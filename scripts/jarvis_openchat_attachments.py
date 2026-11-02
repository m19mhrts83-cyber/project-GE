#!/usr/bin/env python3
"""Private OpenChat backup worker. Default: local status, no login/network.

--apply acquires the existing LINE session lock (never pauses the watcher itself).
No QR login, AI calls, OneDrive binary copies or member-facing publication.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'line_unofficial_poc'))
from openchat_attachments import Queue

PROJECT = 'https://mwubzgefkkjjbingrmqu.supabase.co'
STORAGE = 'https://mwubzgefkkjjbingrmqu.storage.supabase.co'
BUCKET = 'openchat-attachments'
CHUNK = 6*1024*1024
MAX_FILE = 500*1024*1024
# Safety headroom below the plan allowance; not a billing/spend-cap guarantee.
DEFAULT_BUDGET = 80_000_000_000

class Failure(Exception):
    def __init__(self, code, state='retry'):
        self.code,self.state=code,state
        super().__init__(code)

def checksum(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(CHUNK),b''): h.update(chunk)
    return h.hexdigest()

def sniff(path, kind):
    with path.open('rb') as f: data=f.read(1024)
    head=data.lstrip().lower()
    if not data or head.startswith((b'<!doctype html',b'<html',b'<script')):
        raise Failure('non_file_response','invalid')
    if data.startswith(b'%PDF-'): return 'application/pdf'
    if data.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
    if data.startswith((b'GIF87a',b'GIF89a')): return 'image/gif'
    if data[:4]==b'RIFF' and data[8:12]==b'WEBP': return 'image/webp'
    if data[:4]==b'RIFF' and data[8:12]==b'WAVE': return 'audio/wav'
    if data[4:8]==b'ftyp':
        if data[8:12] in (b'heic',b'heix',b'mif1',b'hevc'): return 'image/heic'
        return 'audio/mp4' if kind=='audio' else 'video/mp4'
    if data.startswith(b'\x1aE\xdf\xa3'): return 'audio/webm' if kind=='audio' else 'video/webm'
    if data.startswith(b'OggS'): return 'audio/ogg'
    if data.startswith(b'ID3') or (len(data)>1 and data[0]==255 and data[1]&224==224): return 'audio/mpeg'
    if data.startswith(b'PK\x03\x04'): return 'application/zip'
    if kind=='file': return 'application/octet-stream'
    raise Failure('unknown_media_format','unsupported')

def download(cl, job, target, limit, session=None):
    """Stream non-E2EE Square originals directly from OBS (never /preview).

    Metadata/OIDs/URLs are not persisted. Encrypted messages stay unsupported.
    Redirects are forbidden to avoid forwarding LINE authentication elsewhere.
    """
    headers=dict(cl.Hraders4Obs)
    # The OBS endpoint expects the original access token; CHRLINE's OA proxy
    # headers can contain an encrypted access token and return empty media bodies.
    headers['X-Line-Access']=cl.authToken
    http=session or requests
    response=http.get('https://obs.line-apps.com/r/g2/m/'+job['message_id'],
      headers=headers,stream=True,allow_redirects=False,timeout=(15,90))
    try:
        if response.status_code in (404,410): raise Failure('source_unavailable','expired')
        if response.status_code != 200: raise Failure('source_http_'+str(response.status_code))
        length=response.headers.get('Content-Length')
        if length:job['source_bytes']=int(length)
        if length and int(length)>limit: raise Failure('file_size_limit','held')
        size=0
        with target.open('wb') as f:
            for chunk in response.iter_content(1024*1024):
                size+=len(chunk)
                if size>limit: raise Failure('file_size_limit','held')
                f.write(chunk)
        if not size: raise Failure('empty_file','invalid')
        if length and size!=int(length): raise Failure('incomplete_download')
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally: response.close()

class Store:
    def __init__(self, session=None):
        if os.environ.get('SUPABASE_URL','').rstrip('/')!=PROJECT: raise ValueError('wrong_supabase_project')
        key=os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')
        if not key: raise ValueError('service_key_required')
        self.http=session or requests.Session()
        self.auth={'apikey':key,'Authorization':'Bearer '+key}

    def request(self, method, url, **kwargs):
        r=self.http.request(method,url,headers={**self.auth,**kwargs.pop('headers',{})},
                            timeout=(15,120),allow_redirects=False,**kwargs)
        if not r.ok: raise Failure('storage_http_'+str(r.status_code))
        return r

    def usage(self):
        value=self.request('POST',PROJECT+'/rest/v1/rpc/openchat_backup_storage_bytes',json={}).json()
        if type(value) is not int or value<0: raise Failure('storage_usage_unknown','held')
        return value

    def check_private(self):
        row=self.request('GET',PROJECT+'/storage/v1/bucket/'+BUCKET).json()
        if row.get('id')!=BUCKET or row.get('public') is not False:
            raise Failure('private_bucket_required','held')

    def valid_upload_url(self, url):
        p=urlsplit(url)
        if p.scheme!='https' or p.netloc!=urlsplit(STORAGE).netloc or not p.path.startswith('/storage/v1/upload/resumable/') or p.query or p.fragment:
            raise Failure('invalid_upload_location','held')
        return url

    def remote_hash(self, path):
        r=self.http.request('GET',PROJECT+'/storage/v1/object/'+BUCKET+'/'+path,
          headers=self.auth,stream=True,allow_redirects=False,timeout=(15,120))
        try:
            if r.status_code==404: return None
            if r.status_code==400:
                try:
                    if str(r.json().get('statusCode'))=='404': return None
                except (ValueError,AttributeError): pass
            if r.status_code!=200: raise Failure('verification_http_'+str(r.status_code))
            h=hashlib.sha256()
            for chunk in r.iter_content(CHUNK): h.update(chunk)
            return h.hexdigest()
        finally: r.close()

    def upload(self, queue, job, file):
        digest=checksum(file);path='objects/'+digest
        size=file.stat().st_size
        old=self.remote_hash(path)
        if old is not None:
            if old!=digest: raise Failure('stored_hash_mismatch','invalid')
            return path,digest
        url=job.get('upload_url')
        offset=0
        if url:
            self.valid_upload_url(url)
            r=self.http.request('HEAD',url,headers={**self.auth,'Tus-Resumable':'1.0.0'},allow_redirects=False,timeout=30)
            if r.status_code in (404,410): url=None
            elif r.ok: offset=int(r.headers['Upload-Offset'])
            else: raise Failure('upload_resume_failed')
        if not url:
            meta={'bucketName':BUCKET,'objectName':path,'contentType':job['mime'],'cacheControl':'3600'}
            encoded=','.join(k+' '+base64.b64encode(v.encode()).decode() for k,v in meta.items())
            r=self.request('POST',STORAGE+'/storage/v1/upload/resumable',headers={
              'Tus-Resumable':'1.0.0','Upload-Length':str(size),'Upload-Metadata':encoded,'x-upsert':'false'})
            url=self.valid_upload_url(r.headers.get('Location',''))
            queue.update(job['id'],upload_url=url)
        if not 0<=offset<=size: raise Failure('invalid_upload_offset','held')
        with file.open('rb') as f:
            f.seek(offset)
            while offset<size:
                chunk=f.read(CHUNK)
                r=self.request('PATCH',url,data=chunk,headers={
                  'Tus-Resumable':'1.0.0','Upload-Offset':str(offset),'Content-Type':'application/offset+octet-stream'})
                offset+=len(chunk)
                if int(r.headers.get('Upload-Offset','-1'))!=offset: raise Failure('invalid_upload_offset')
        if self.remote_hash(path)!=digest: raise Failure('stored_hash_mismatch','invalid')
        return path,digest

    def metadata(self, job, path, digest):
        row={k:job[k] for k in ['id','room_id','message_id','thread_id','kind']}
        row.update(original_name=job['filename'],content_type=job['mime'],byte_size=job['bytes'],sha256=digest,bucket=BUCKET,storage_path=path)
        self.request('POST',PROJECT+'/rest/v1/openchat_attachments',json=row,
          headers={'Prefer':'resolution=merge-duplicates'},params={'on_conflict':'id'})

def process(queue, store, fetch, *, limit=10, max_file=MAX_FILE, budget=DEFAULT_BUDGET, spool_limit=2*1024**3):
    # One worker process at a time (CLI also holds the LINE session lock).
    for job in queue.due(limit):
        file=queue.root/(job['id']+'.media')
        try:
            if job['source_bytes'] and job['source_bytes']>max_file: raise Failure('file_size_limit','held')
            reserve=file.stat().st_size if file.exists() else job['source_bytes'] or max_file
            if store.usage()+reserve>budget: raise Failure('storage_budget','held')
            if not file.exists():
                used=sum(p.stat().st_size for p in queue.root.glob('*.media'))
                if used+max_file>spool_limit or shutil.disk_usage(queue.root).free<max_file+64*1024**2:
                    raise Failure('local_capacity','held')
                temp=file.with_suffix('.part')
                temp.unlink(missing_ok=True)
                fetch(job,temp,max_file)
                temp.chmod(0o600)
                if not 0<temp.stat().st_size<=max_file: raise Failure('file_size_limit','held')
                temp.replace(file)
            size=file.stat().st_size
            queue.update(job['id'],source_bytes=job.get('source_bytes') or size)
            if store.usage()+size>budget: raise Failure('storage_budget','held')
            job.update(bytes=size,mime=sniff(file,job['kind']))
            queue.update(job['id'],bytes=size,mime=job['mime'])
            path,digest=store.upload(queue,job,file)
            store.metadata(job,path,digest)
            queue.update(job['id'],state='saved',sha256=digest,storage_path=path,error=None,upload_url=None,saved_at=time.time())
            file.unlink() # only the verified temporary spool, never the archived original
        except Exception as e:
            code=e.code if isinstance(e,Failure) else 'transfer_failed'
            state=e.state if isinstance(e,Failure) else 'retry'
            attempts=job['attempts']+1
            queue.update(job['id'],state=state,attempts=attempts,error=code,
                         next_at=time.time()+min(86400,60*2**min(attempts,10)),source_bytes=job.get('source_bytes'))
        finally: file.with_suffix('.part').unlink(missing_ok=True)
    return queue.report()

def fetch_recent(cl, chat, thread='', sync='', cont=''):
    """Use the installed SDK sender with documented BACKWARD=2, not its fixed FORWARD wrapper."""
    from chrline_client_utils import chrline_throttle
    chrline_throttle()
    params=[[10,1,0],[11,2,chat],[11,3,sync or None],[8,4,100],
            [8,5,2],[8,6,1],[11,7,cont or None],[8,8,1],[11,9,thread or None]]
    return getattr(cl,'_SquareService__sender').send('fetchSquareChatEvents',params)

def scan(cl, queue, routes_file, *, pages=2, active_threads=None, thread_limit=10, progress=None, text_state=None):
    """Recent page every run plus a separate, resumable backward history cursor."""
    from chrline_open_chat_to_md import (_parse_routes,_get,_best_message_from_event,
        _extract_events,_extract_tokens,_extract_thread_mids_from_event,_is_thread_deleted_error)
    queue.db.execute('CREATE TABLE IF NOT EXISTS streams (id TEXT PRIMARY KEY, sync TEXT, continuation TEXT, updated REAL, error TEXT)')
    queue.db.execute('CREATE TABLE IF NOT EXISTS targets (room TEXT, thread TEXT, touched REAL NOT NULL DEFAULT 0, closed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(room,thread))')
    queue.db.execute('CREATE TABLE IF NOT EXISTS recent_heads (id TEXT PRIMARY KEY, sync TEXT, continuation TEXT)')
    queue.db.commit()
    stats={'streams_ok':0,'streams_failed':0,'messages':0,'pages_remaining':0,'threads_deferred':0}
    anchors={}
    if text_state and Path(text_state).exists():anchors=json.loads(Path(text_state).read_text()).get('streams',{})
    active={}
    if active_threads and Path(active_threads).exists():
        active=json.loads(Path(active_threads).read_text());active=active.get('routes',active)
    for route in _parse_routes(Path(routes_file)):
        threads=set();raw=active.get(route.rid,[]) if isinstance(active,dict) else []
        if isinstance(raw,dict):raw=raw.get('thread_mids',[])
        if isinstance(raw,list):threads.update(t for t in raw if isinstance(t,str))
        todo=[''];seen=set()
        while todo:
            thread=todo.pop(0)
            if thread in seen:continue
            seen.add(thread)
            key=hashlib.sha256(('backward-v3\0'+route.square_chat_mid+'\0'+thread).encode()).hexdigest()
            old=queue.db.execute('SELECT * FROM streams WHERE id=?',(key,)).fetchone()
            sync,cont=(old['sync'],old['continuation']) if old else ('','')
            def consume(result,cohort):
                events=_extract_events(cl,result)
                for event in events:
                    if not thread:threads.update(_extract_thread_mids_from_event(event,route.square_chat_mid))
                    msg=_best_message_from_event(cl,event)
                    if msg is None:continue
                    stats['messages']+=1;ct=_get(cl,msg,'contentType',15)
                    if ct not in (1,2,3,14):continue
                    queue.enqueue(room_id=route.square_chat_mid,message_id=str(_get(cl,msg,'id',4) or ''),thread_id=thread,
                      content_type=ct,metadata=_get(cl,msg,'contentMetadata',18),encrypted=bool(_get(cl,msg,'chunks',20)),cohort=cohort)
                return events
            try:
                anchor_key=route.square_chat_mid+('::thread::'+thread if thread else '::main')
                anchor=str(anchors.get(anchor_key,{}).get('sync_token') or '')
                head=queue.db.execute('SELECT * FROM recent_heads WHERE id=?',(key,)).fetchone()
                recent=None
                if head:
                    from chrline_open_chat_to_md import _fetch_square_chat_events
                    hs,hc=head['sync'],head['continuation']
                    for _ in range(max(1,pages)):
                        result=_fetch_square_chat_events(cl,square_chat_mid=route.square_chat_mid,thread_mid=thread or None,
                          sync_token=hs,cont_token=hc,limit=100)
                        new_events=consume(result,'daily')
                        ns,nc=_extract_tokens(cl,result,hs,hc)
                        if not new_events or (ns==hs and nc==hc):nc=''
                        hs,hc=ns,nc
                        with queue.db:queue.db.execute('INSERT OR REPLACE INTO recent_heads VALUES (?,?,?)',(key,hs,hc))
                        if not hc:break
                    if hc:stats['pages_remaining']+=1
                else:
                    recent=fetch_recent(cl,route.square_chat_mid,thread,anchor)
                    events=consume(recent,'daily' if old else 'backfill')
                    if anchor:
                        with queue.db:queue.db.execute('INSERT OR REPLACE INTO recent_heads VALUES (?,?,?)',(key,anchor,''))
                if old is None:
                    if recent is None:
                        recent=fetch_recent(cl,route.square_chat_mid,thread,anchor)
                        events=consume(recent,'backfill')
                    sync,cont=_extract_tokens(cl,recent,'','')
                    if not events:cont=''
                    with queue.db:queue.db.execute('INSERT OR REPLACE INTO streams VALUES (?,?,?,?,?)',(key,sync or '',cont or '',time.time(),None))
                # Empty continuation means history is complete; recent still runs next time.
                for _ in range(pages):
                    if not cont:break
                    result=fetch_recent(cl,route.square_chat_mid,thread,sync,cont)
                    events=consume(result,'backfill')
                    next_sync,next_cont=_extract_tokens(cl,result,sync,cont)
                    if not events or (next_sync==sync and next_cont==cont):next_cont=''
                    sync,cont=next_sync,next_cont
                    with queue.db:queue.db.execute('INSERT OR REPLACE INTO streams VALUES (?,?,?,?,?)',(key,sync or '',cont or '',time.time(),None))
                stats['streams_ok']+=1
                if cont:stats['pages_remaining']+=1
            except Exception as exc:
                stats['streams_failed']+=1
                with queue.db:queue.db.execute('INSERT OR REPLACE INTO streams VALUES (?,?,?,?,?)',(key,sync or '',cont or '',time.time(),'scan_failed'))
                if thread and _is_thread_deleted_error(exc):
                    with queue.db:queue.db.execute('UPDATE targets SET closed=1 WHERE room=? AND thread=?',(route.square_chat_mid,thread))
            if thread:
                with queue.db:queue.db.execute('UPDATE targets SET touched=? WHERE room=? AND thread=?',(time.time(),route.square_chat_mid,thread))
            else:
                with queue.db:queue.db.executemany('INSERT OR IGNORE INTO targets(room,thread) VALUES (?,?)',[(route.square_chat_mid,t) for t in threads if t.startswith('t')])
                candidates=list(queue.db.execute('SELECT thread FROM targets WHERE room=? AND closed=0 ORDER BY touched,thread',(route.square_chat_mid,)))
                todo.extend(r['thread'] for r in candidates[:thread_limit]);stats['threads_deferred']+=max(0,len(candidates)-thread_limit)
        if progress:progress(dict(stats))
    return stats

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--limit',type=int,default=10)
    p.add_argument('--max-file-mib',type=int,default=50)
    p.add_argument('--budget-bytes',type=int,default=DEFAULT_BUDGET)
    p.add_argument('--retry-held',action='store_true',help='Requeue capacity-held jobs only with --apply')
    p.add_argument('--scan',action='store_true',help='Scan attachment source events with independent cursors')
    p.add_argument('--routes-yaml',type=Path)
    p.add_argument('--scan-pages',type=int,default=2)
    p.add_argument('--active-threads',type=Path)
    p.add_argument('--scan-threads',type=int,default=10)
    a=p.parse_args()
    if not 1<=a.limit<=100 or not 1<=a.max_file_mib<=500 or not 0<a.budget_bytes<=DEFAULT_BUDGET or not 0<=a.scan_pages<=20 or not 0<=a.scan_threads<=50:
        p.error('invalid limit or capacity setting')
    q=Queue()
    try:
        if not a.apply:
            print(json.dumps(q.report()));return 0
        import fcntl
        with (q.root/'worker.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            from chrline_client_utils import open_chat_session_lock,save_root_from_env,build_logged_in_client,chrline_throttle
            with open_chat_session_lock(save_root_from_env(),blocking=False):
                store=Store();store.check_private()
                if a.retry_held:
                    with q.db: q.db.execute("UPDATE jobs SET state='pending',next_at=0 WHERE state='held'")
                cl=build_logged_in_client(save_root_from_env(),allow_qr_login=False)
                scanned=None
                if a.scan:
                    if not a.routes_yaml:p.error('--scan requires --routes-yaml')
                    scanned=scan(cl,q,a.routes_yaml,pages=a.scan_pages,active_threads=a.active_threads,thread_limit=a.scan_threads,text_state=save_root_from_env()/'.chrline_open_chat_state.json')
                    print(json.dumps({'scan':scanned}),flush=True)
                def fetch(job,path,size):
                    chrline_throttle()
                    return download(cl,job,path,size)
                report=process(q,store,fetch,limit=a.limit,max_file=a.max_file_mib*1024**2,budget=a.budget_bytes)
                report['project_storage_bytes']=store.usage()
                print(json.dumps(report))
                return 1 if (scanned and scanned['streams_failed']) or any(report['states'].get(k,0) for k in ('retry','held','invalid','unsupported')) else 0
    except BlockingIOError:
        print('OpenChat session/worker busy; no competing login attempted',file=sys.stderr);return 75
    except Exception:
        print('OpenChat attachment worker unavailable; check configuration/session',file=sys.stderr);return 1
    finally:q.close()

if __name__=='__main__': raise SystemExit(main())
