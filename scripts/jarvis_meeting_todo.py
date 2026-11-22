#!/usr/bin/env python3
"""714 prepared minutes -> saved Notion -> 312. No AI, no new DB/table.

Only dispatch() posts proposals. Extraction/backtest functions are read-only.
JSON state and meeting contents must stay under ignored .jarvis_state/.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUTBOX = REPO / '.jarvis_state' / 'meeting_todo_outbox.json'
PREFIX = 'meeting_todo:v1:'
from jarvis_meeting_owner import load_owner_policy, resolve_assignee



def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, data: Any):
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=path.name)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def load_json(path: Path, default=None):
    # Corrupt state must stop the operation, never silently forget terminal decisions.
    return json.loads(path.read_text()) if path.exists() else ({} if default is None else default)


def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(text))).strip().casefold()


def candidate(meeting_id: str, item: dict):
    todo = str(item.get('todo') or '').strip()
    assignee = str(item.get('assignee') or '').strip()
    evidence = str(item.get('evidence') or '').strip()
    if not todo or not evidence or not meeting_id:
        raise ValueError('meeting_id/todo/evidence required')
    inference = item.get('owner_inference') if isinstance(item.get('owner_inference'), dict) else None
    resolution = resolve_assignee(meeting_id, assignee, load_owner_policy(), inference)
    mine = resolution["identity"] == "owner"
    identity = 'owner' if mine else normalize(assignee or 'unknown')
    cid = hashlib.sha256(('v1\0'+meeting_id+'\0'+normalize(todo)+'\0'+identity).encode()).hexdigest()
    due = item.get('due_date') or None
    if due:
        date.fromisoformat(due)
        if due not in str(item.get('due_raw') or ''):
            # Relative/short dates need explicit confirmation before an ISO date is applied.
            if item.get('due_confirmed') is not True:
                due = None
    return {'candidate_id':cid,'meeting_id':meeting_id,'todo':todo,'title':todo[:200],
            'assignee':assignee,'owner_inference':inference,'owner_confirmed':mine,'owner_resolution':resolution,'evidence':evidence,
            'due_raw':str(item.get('due_raw') or ''),'due_date':due,'due_confirmed':item.get('due_confirmed') is True,
            'level': 'L2' if due else 'L1','lane':str(item.get('lane') or 'ai_raimo'),
            'status':'queued' if mine else 'excluded' if resolution['identity']=='other' else 'held'}


def prepared(data: dict, meeting_id: str):
    if data.get('meeting_id') != meeting_id or data.get('extracted') is not True:
        raise ValueError('prepared meeting_id/extracted mismatch')
    body = str(data.get('body') or '')
    if not body or not all(h in body for h in ('ひとことで','決まったこと','ToDo','次回')):
        raise ValueError('52_ formatted minutes required')
    if not isinstance(data.get('candidates'), list):
        raise ValueError('candidates must be a list (including an explicit empty list)')
    cs = {c['candidate_id']: c for c in (candidate(meeting_id,x) for x in data['candidates'])}
    return {**data,'body':body,'candidates':list(cs.values())}


def enqueue(artifact: dict, notion: dict, path: Path = OUTBOX):
    if not notion.get('page_id') or not notion.get('notion_url'):
        raise ValueError('Notion save must succeed before handoff')
    state = load_json(path)
    for c in artifact['candidates']:
        state.setdefault(c['candidate_id'],{**c,'notion_page_id':notion['page_id'],
            'notion_url':notion['notion_url'],'project_url':artifact.get('project_url',''),
            'saved_at':notion.get('at') or now(),'extracted':True,'outbox_at':now()})
    atomic_json(path,state)


class Store:
    """Existing sync_meta value TEXT; CAS by monotonic updated_at (small URL)."""
    def __init__(self):
        self.base = (os.getenv('JARVIS_SUPABASE_URL') or '').rstrip('/')
        self.token = os.getenv('JARVIS_SUPABASE_SERVICE_ROLE_KEY') or ''
        self.versions = {}
        if not self.base or not self.token: raise RuntimeError('Supabase configuration missing')
    def request(self, method, params, body=None, prefer='return=representation'):
        req=urllib.request.Request(self.base+'/rest/v1/sync_meta?'+urllib.parse.urlencode(params),
            data=None if body is None else json.dumps(body).encode(),method=method,
            headers={'apikey':self.token,'Authorization':'Bearer '+self.token,'Content-Type':'application/json','Prefer':prefer})
        with urllib.request.urlopen(req,timeout=30) as r:
            return json.loads(r.read() or b'[]')
    def get(self,cid):
        rows=self.request('GET',{'key':'eq.'+PREFIX+cid,'select':'value,updated_at'})
        if rows: self.versions[cid]=(rows[0]['value'],rows[0]['updated_at'])
        return rows[0]['value'] if rows else None
    def insert(self,cid,row):
        self.request('POST',{'on_conflict':'key'},{'key':PREFIX+cid,'value':json.dumps(row,ensure_ascii=False)},
                     'resolution=ignore-duplicates,return=representation')
    def cas(self,cid,old,row):
        from datetime import timedelta
        prior=self.versions.get(cid)
        if not prior or prior[0]!=old:return False
        stamp=max(datetime.now(timezone.utc),datetime.fromisoformat(prior[1].replace('Z','+00:00'))+timedelta(microseconds=1)).isoformat()
        raw=json.dumps(row,ensure_ascii=False)
        rows=self.request('PATCH',{'key':'eq.'+PREFIX+cid,'updated_at':'eq.'+prior[1]},
                          {'value':raw,'updated_at':stamp})
        if rows:self.versions[cid]=(raw,stamp)
        return bool(rows)


def dispatch(store=None, poster=None, path: Path=OUTBOX, limit=3):
    """Retry only known-unsent records. An uncertain Slack send is never resent automatically."""
    from jarvis_todoist_312_slack_blocks import build_create_blocks, post_slack, prefer_url_mode, _action_secret, _bot_token
    if os.getenv('JARVIS_MEETING_TODO_DISABLE','').lower() in {'1','true','yes'}:
        return {'posted':0,'disabled':True}
    state=load_json(path)
    # Re-check queued owners against the current private policy before any cloud write.
    policy=load_owner_policy()
    changed=False
    for c in state.values():
        if c.get('status')!='queued':continue
        resolution=resolve_assignee(c['meeting_id'],c.get('assignee',''),policy,c.get('owner_inference'))
        if resolution['identity']!='owner':
            c.update(owner_confirmed=False,owner_resolution=resolution,
                     status='excluded' if resolution['identity']=='other' else 'held')
            changed=True
    if changed:atomic_json(path,state)
    if not any(c.get('status')=='queued' for c in state.values()): return {'posted':0,'held':sum(c['status']=='held' for c in state.values())}
    if poster is None:
        if not _action_secret(): raise RuntimeError('312 signing key missing; no proposal posted')
        if not _bot_token() and not os.getenv('SLACK_WEBHOOK_AI_TEAM_CONSULT'):
            raise RuntimeError('consult destination missing; do not fall back to report')
    store=store or Store(); poster=poster or (lambda p:post_slack(p,dry_run=False))
    posted=0
    for cid,c in state.items():
        if c['status']!='queued' or not c.get('owner_confirmed'):continue
        if not c.get('notion_page_id') or not c.get('notion_url') or c.get('extracted') is not True:
            raise ValueError('unsaved/unextracted candidate')
        store.insert(cid,c)
        raw=store.get(cid)
        if raw is None:raise RuntimeError('candidate persistence failed')
        row=json.loads(raw)
        if row['status']!='queued':continue
        if posted>=limit:break
        # Durable pre-send marker protects against a process crash after Slack accepted the card.
        sending={**row,'status':'posting','posting_at':now()}
        if not store.cas(cid,raw,sending):continue
        it={**row,'n':1,'origin':'meeting714','project_url':row['notion_url']}
        payload=build_create_blocks([it],header_text='【相談】312 Todoist起票整理',
            fallback_text='本人担当の候補1件。起票／見送りを選んでください。',url_mode=prefer_url_mode())
        try:
            rc=poster(payload)
        except Exception:
            # Keep posting: unknown delivery, manual reconciliation needed.
            raise RuntimeError('Slack delivery uncertain; do not resend') from None
        if rc!=0:raise RuntimeError('Slack delivery uncertain; do not resend')
        current=store.get(cid)
        if current and json.loads(current)['status']=='posting':
            if not store.cas(cid,current,{**sending,'status':'posted','posted_at':now()}):
                raise RuntimeError('Slack sent but state changed; reconcile before resend')
        posted+=1
    return {'posted':posted,'held':sum(c['status']=='held' for c in state.values())}


def notify_ops():
    """Generic failure only: never send meeting text or credentials to diagnostics."""
    url=os.getenv('SLACK_WEBHOOK_AI_TEAM_OPS')
    if not url: return
    req=urllib.request.Request(url,data=json.dumps({'text':'【ops】312 Todoist起票整理\n714候補の受け渡しに失敗・要照合。結果不明の投稿/起票は再送しません。'}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=15) as r:
            if r.status>=400: raise RuntimeError('ops notification failed')
    except Exception:
        import sys
        print('714->312 ops notification unavailable',file=sys.stderr)


def extract_only(meeting: dict):
    """Conservative deterministic backtest; no signals or inferred speaker ownership."""
    import jarvis_todoist_sb_propose as sb
    summary=str(meeting.get('summary') or '')
    items=[]
    # Genspark's localized/numbered action section is not always "## Action Items".
    action = re.search(r'(?im)^#{1,3}\s*(?:\d+[.．]\s*)?(?:Action\s*Items?|アクションアイテム|宿題|タスク)\s*\n(.*?)(?=^#{1,2}\s|\Z)',summary,re.S)
    if action:
        for m in sb.BULLET_RE.finditer(action.group(1)):
            raw=m.group(1).strip()
            parsed=sb.ASSIGNEE_ITEM_RE.match(raw)
            if parsed:
                assignee,todo=parsed.group(1),parsed.group(2)
            else:
                assignee,todo='',raw
            items.append({'todo':todo,'assignee':assignee,'evidence':raw})
    # The curated 52_ format's ToDo table is also accepted (no re-extraction in dispatch).
    match=re.search(r'(?im)^##\s*(?:ToDo|TODO|タスク).*?\n(.*?)(?=^##\s|\Z)',summary,re.S)
    if match:
        for line in match.group(1).splitlines():
            cols=[v.strip() for v in line.strip().strip('|').split('|')]
            if len(cols)>=2 and not re.fullmatch(r'[-: ]+',cols[0]) and cols[0] not in ('誰が','担当','担当者'):
                items.append({'todo':cols[1],'assignee':cols[0],'evidence':line,'due_raw':cols[2] if len(cols)>2 else ''})
    return list({c['candidate_id']:c for c in (candidate(str(meeting['id']),x) for x in items)}.values())
