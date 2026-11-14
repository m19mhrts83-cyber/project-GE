"""Local-only synthetic Supabase HTTP fixture; never connects to a live service."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs,unquote
from datetime import datetime,timezone,timedelta
from pathlib import Path
import base64,json,sys,hashlib,io
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jarvis_asset_618_readback import row_digest
OWNER='11111111-1111-4111-8111-111111111111';RUN='22222222-2222-4222-8222-222222222222';PROOF='33333333-3333-4333-8333-333333333333'
row={'account_id':'sbi_index','as_of':'2026-11-14','value_jpy':123000,'source':'weekly_web'}
check={'status':'verified','record_as_of':row['as_of'],'source_as_of':None,'row_digest':row_digest('portfolio_snapshots',row),'checked_at':'2026-11-14T00:01:00Z'}
context={'run_id':RUN,'target_ids':['sbi_index','axa_life'],'numeric_readbacks':{'portfolio_snapshots':{'sbi_index':check}}}
image=Image.new('RGB',(1000,420),'#f2f6fa');draw=ImageDraw.Draw(image);draw.text((55,60),'618 TEST FIXTURE / NOT REAL FINANCIAL DATA',fill='#183550');draw.text((55,120),'Synthetic evidence: reviewed account / contract / date',fill='#183550');draw.text((55,200),'2026-11-14   fixture only',fill='#183550');buf=io.BytesIO();image.save(buf,format='PNG');PNG=buf.getvalue()
TABLES={'asset_evidence_owners':[{'user_id':OWNER}], 'portfolio_accounts':[{'id':'sbi_index','name':'検証用 SBI','kind':'securities','institution':'fixture','ingest':'fixture','active':True}], 'portfolio_snapshots':[row], 'liquidity_accounts':[], 'liquidity_snapshots':[], 'sync_meta':[{'key':'portfolio_weekly_summary','value':json.dumps({'asset_618':context})}], 'asset_618_display_checks':[], 'asset_evidence_latest':[{'id':PROOF,'owner_id':OWNER,'account_scope':'portfolio','account_id':'sbi_index','contract_key':'primary','view_key':'balance','active_slot':'a','storage_path':f'618/latest/{OWNER}/portfolio/sbi_index/primary/balance.a.png','sha256':hashlib.sha256(PNG).hexdigest(),'captured_at':'2026-11-14T00:00:00Z','source_as_of':'2026-11-13','last_attempt_at':'2026-11-14T01:00:00Z','last_attempt_status':'failed'}]}
MODE='normal'
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,status,data,kind='application/json'):
  raw=json.dumps(data).encode() if kind=='application/json' else data
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def user(self):
  try:return json.loads(base64.urlsafe_b64decode(self.headers.get('Authorization','').split('.')[1]+'==')).get('sub')
  except Exception:return None
 def do_GET(self):
  u=urlparse(self.path);qs=parse_qs(u.query)
  if u.path=='/auth/v1/user':return self.send(200,{'id':self.user(),'aud':'authenticated','role':'authenticated','email':'fixture@example.invalid','app_metadata':{},'user_metadata':{},'created_at':'2026-11-14T00:00:00Z','identities':[]})
  if u.path.startswith('/rest/v1/'):
   table=u.path.split('/')[-1]
   if MODE=='unavailable' and table=='asset_evidence_latest':return self.send(503,{'message':'fixture unavailable'})
   rows=TABLES.get(table,[])
   rows=[dict(r) for r in rows]
   if table in ('asset_evidence_owners','asset_evidence_latest','asset_618_display_checks'):
    key='user_id' if table=='asset_evidence_owners' else 'owner_id';rows=[r for r in rows if r.get(key)==self.user()]
   for k,values in qs.items():
    v=values[0]
    if v.startswith('eq.'):
     expected=v[3:];rows=[r for r in rows if str(r.get(k)).lower()==expected.lower()]
    if v.startswith('in.('):rows=[r for r in rows if str(r.get(k)) in v[4:-1].split(',')]
    if v.startswith('gte.'):rows=[r for r in rows if str(r.get(k,''))>=v[4:]]
    if v.startswith('lte.'):rows=[r for r in rows if str(r.get(k,''))<=v[4:]]
   return self.send(200,rows)
  if u.path.startswith('/storage/v1/object/'):
   if self.user()!=OWNER:return self.send(403,{})
   return self.send(200,b'corrupt' if MODE=='bad_image' else PNG,'image/png')
  return self.send(404,{})
 def do_POST(self):
  global MODE
  data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
  if self.path=='/__fixture/mode':
   MODE=data['mode'];TABLES['portfolio_snapshots'][0]['value_jpy']=999 if MODE=='changed_db' else 123000
   return self.send(200,{'mode':MODE})
  if self.path.startswith('/rest/v1/asset_618_display_checks'):
   if self.user()!=OWNER:return self.send(403,{})
   TABLES['asset_618_display_checks']=[data];return self.send(201,[data])
  return self.send(404,{})
ThreadingHTTPServer(('127.0.0.1',6418),Handler).serve_forever()
