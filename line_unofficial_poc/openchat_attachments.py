"""Private, local durable queue. No network, auth imports or AI calls at enqueue time."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

KINDS = {1: 'image', 2: 'video', 3: 'audio', 14: 'file'}

def private_root(path=None):
    root = Path(path or os.environ.get('LINE_OPENCHAT_ATTACHMENTS_DIR') or
                Path.home()/'.local/share/jarvis/openchat-attachments').expanduser().resolve()
    if any(x in str(root).lower() for x in ['onedrive', 'googledrive', 'google drive', 'dropbox', 'mobile documents', 'icloud']):
        raise ValueError('spool_must_not_sync_to_cloud')
    if root in (Path('/'),Path.home(),Path.home().parent,Path('/tmp'),Path('/var/tmp')):
        raise ValueError('dedicated_spool_directory_required')
    if root.exists():
        known = re.compile(r'(queue\.sqlite3(?:-journal|-wal|-shm)?|worker\.lock|[0-9a-f]{64}\.(media|part))')
        if any(p.is_symlink() or not known.fullmatch(p.name) for p in root.iterdir()):
            raise ValueError('dedicated_spool_directory_required')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root

class Queue:
    def __init__(self, root=None):
        self.root = private_root(root)
        self.path = self.root/'queue.sqlite3'
        self.db = sqlite3.connect(self.path, timeout=10)
        self.path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, room_id TEXT NOT NULL, message_id TEXT NOT NULL,
          thread_id TEXT NOT NULL, kind TEXT NOT NULL, filename TEXT NOT NULL,
          source_bytes INTEGER, state TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
          created_at REAL NOT NULL, error TEXT, sha256 TEXT, bytes INTEGER,
          mime TEXT, storage_path TEXT, upload_url TEXT,
          cohort TEXT NOT NULL DEFAULT 'backfill', saved_at REAL)''')
        self.db.commit()

    def close(self): self.db.close()

    def enqueue(self, *, room_id, message_id, thread_id='', content_type, metadata=None, encrypted=False, cohort='backfill'):
        if content_type not in KINDS: return None
        if cohort not in ('backfill','daily'): raise ValueError('invalid_cohort')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', str(room_id)) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', str(message_id)):
            raise ValueError('invalid_source_identity')
        if thread_id and not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', str(thread_id)):
            raise ValueError('invalid_thread')
        meta = metadata if isinstance(metadata, dict) else {}
        filename = str(meta.get('FILE_NAME') or meta.get('filename') or '')
        filename = re.split(r'[/\\]', filename)[-1]
        filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)[:255] or KINDS[content_type]
        size = meta.get('FILE_SIZE') or meta.get('fileSize')
        try: size = int(size) if size is not None else None
        except (TypeError, ValueError): size = None
        if size is not None and size < 0: size = None
        ident = hashlib.sha256(f'{room_id}\0{message_id}'.encode()).hexdigest()
        state = 'unsupported' if encrypted else 'pending'
        with self.db:
            self.db.execute('''INSERT OR IGNORE INTO jobs
              (id,room_id,message_id,thread_id,kind,filename,source_bytes,state,created_at,error,cohort)
              VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (ident,str(room_id),str(message_id),str(thread_id),
              KINDS[content_type],filename,size,state,time.time(),'encrypted_media_requires_adapter' if encrypted else None,cohort))
        return ident

    def update(self, ident, **values):
        if set(values)-{'state','attempts','next_at','error','sha256','bytes','mime','storage_path','upload_url','saved_at'}:
            raise ValueError('invalid_queue_update')
        with self.db:
            self.db.execute('UPDATE jobs SET '+','.join(f'{k}=?' for k in values)+' WHERE id=?', [*values.values(),ident])

    def due(self, limit=10):
        return [dict(row) for row in self.db.execute('''SELECT * FROM jobs
          WHERE state IN ('pending','retry') AND next_at <= ?
          ORDER BY CASE kind WHEN 'file' THEN 0 WHEN 'image' THEN 1 WHEN 'audio' THEN 2 ELSE 3 END,created_at
          LIMIT ?''',(time.time(),limit))]

    def report(self):
        unique=list(self.db.execute("SELECT sha256,max(bytes) AS bytes,min(saved_at) AS first_saved,max(cohort='backfill') AS backfill FROM jobs WHERE state='saved' GROUP BY sha256"))
        first=self.db.execute("SELECT min(created_at) FROM jobs WHERE cohort='daily'").fetchone()[0]
        days=min(30,max(0,(time.time()-first)/86400)) if first else 0
        daily_bytes=sum(r['bytes'] for r in unique if not r['backfill'] and r['first_saved']>=time.time()-30*86400)
        oldest=self.db.execute("SELECT min(created_at) FROM jobs WHERE state IN ('pending','retry','held')").fetchone()[0]
        return {'states':dict(self.db.execute('SELECT state,count(*) FROM jobs GROUP BY state').fetchall()),
                'by_kind':[dict(r) for r in self.db.execute('SELECT kind,state,count(*) AS count FROM jobs GROUP BY kind,state')],
                'oldest_waiting_seconds':round(time.time()-oldest) if oldest else None,
                'saved_unique_bytes':sum(r['bytes'] for r in unique),
                'backfill_unique_bytes':sum(r['bytes'] for r in unique if r['backfill']),
                'daily_last30_unique_bytes':daily_bytes,'daily_observation_days':round(days,2),
                'projected_monthly_bytes':round(daily_bytes/days*30) if days>=2 else None}

def capture(msg, *, getter, room_id, thread_id='', dry_run=False):
    """Called before text dedup. Failures are visible but never stop MD ingestion."""
    if dry_run or os.environ.get('LINE_OPENCHAT_ATTACHMENTS_QUEUE') != '1': return
    queue = None
    try:
        ct = getter(msg,'contentType',15)
        if ct not in KINDS: return
        queue = Queue()
        queue.enqueue(room_id=room_id,thread_id=thread_id,
          message_id=str(getter(msg,'id',4) or ''),content_type=ct,
          metadata=getter(msg,'contentMetadata',18),encrypted=bool(getter(msg,'chunks',20)),
          cohort=os.environ.get('LINE_OPENCHAT_ATTACHMENTS_COHORT','backfill'))
    except Exception:
        # Never include an exception body, source URL, credentials or message metadata.
        print('# openchat attachment queue failed; attachment capture needs review',file=sys.stderr)
    finally:
        if queue: queue.close()
