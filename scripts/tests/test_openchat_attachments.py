import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'line_unofficial_poc'))
from openchat_attachments import Queue,capture
spec=importlib.util.spec_from_file_location('attachment_worker',ROOT/'scripts/jarvis_openchat_attachments.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

class FakeStore:
    def __init__(self):self.objects={};self.rows={};self.fails=0;self.usage_bytes=0;self.uploads=0
    def usage(self):return self.usage_bytes
    def upload(self,q,j,file):
        if self.fails:self.fails-=1;raise RuntimeError('must-not-log-token')
        sha=w.checksum(file);path='objects/'+sha
        if path not in self.objects:self.objects[path]=file.read_bytes();self.uploads+=1
        return path,sha
    def metadata(self,j,path,sha):self.rows[j['id']]=(path,sha)

class AttachmentsTest(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.q=Queue(self.temp.name);self.s=FakeStore()
    def tearDown(self):self.q.close();self.temp.cleanup()
    def add(self,mid='1',ct=14,**kw):return self.q.enqueue(room_id='mroom',message_id=mid,content_type=ct,**kw)
    def row(self,ident):return dict(self.q.db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone())
    def pdf(self,j,p,limit):p.write_bytes(b'%PDF-1.7\nfixture')

    def test_queue_dedup_is_independent_of_thread_route_and_does_not_store_raw_metadata(self):
        ident=self.add(metadata={'FILE_NAME':'../../report.pdf','url':'https://example/?secret=never-store'})
        self.assertEqual(ident,self.add(thread_id='thread'))
        self.assertEqual(len(self.q.due()),1)
        self.assertEqual(self.row(ident)['filename'],'report.pdf')
        self.q.db.commit();self.assertNotIn(b'never-store',self.q.path.read_bytes())

    def test_document_image_audio_video_priority_and_encrypted_visibility(self):
        for i,ct in enumerate([2,3,1,14]):self.add(str(i),ct)
        self.assertEqual([j['kind'] for j in self.q.due()],['file','image','audio','video'])
        e=self.add('encrypted',1,encrypted=True)
        self.assertEqual(self.row(e)['state'],'unsupported')
        self.assertEqual(self.q.report()['states']['unsupported'],1)

    def test_capture_disabled_and_dry_run_never_even_create_queue(self):
        with patch.dict(os.environ,{'LINE_OPENCHAT_ATTACHMENTS_QUEUE':'0'}),patch('openchat_attachments.Queue',side_effect=AssertionError):
            capture({},getter=lambda *x:None,room_id='m')
        with patch.dict(os.environ,{'LINE_OPENCHAT_ATTACHMENTS_QUEUE':'1'}),patch('openchat_attachments.Queue',side_effect=AssertionError):
            capture({},getter=lambda *x:None,room_id='m',dry_run=True)

    def test_capture_failure_does_not_stop_md_and_does_not_print_exception(self):
        import io
        err=io.StringIO()
        with patch.dict(os.environ,{'LINE_OPENCHAT_ATTACHMENTS_QUEUE':'1'}),patch('openchat_attachments.Queue',side_effect=RuntimeError('private-token')),patch('sys.stderr',err):
            capture({},getter=lambda *x:1,room_id='m')
        self.assertIn('queue failed',err.getvalue());self.assertNotIn('private-token',err.getvalue())

    def test_enabled_collector_captures_raw_fields_before_text_dedup(self):
        msg={'id':'123','contentType':14,'contentMetadata':{'FILE_NAME':'source.pdf','FILE_SIZE':'12'}}
        with patch.dict(os.environ,{'LINE_OPENCHAT_ATTACHMENTS_QUEUE':'1','LINE_OPENCHAT_ATTACHMENTS_DIR':self.temp.name}):
            for _ in range(2):capture(msg,getter=lambda m,k,f:m.get(k),room_id='mroom',thread_id='thread')
        rows=self.q.due();self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['thread_id'],'thread');self.assertEqual(rows[0]['source_bytes'],12)
        # Realtime/batch adapters invoke the independent queue before their text dedup.
        batch=(ROOT/'line_unofficial_poc/chrline_open_chat_to_md.py').read_text()
        rt=(ROOT/'line_unofficial_poc/chrline_open_chat_realtime_watch.py').read_text()
        self.assertLess(batch.index('capture_attachment(msg,'),batch.index('if dk in seen_dedup:',batch.index('capture_attachment(msg,')))
        self.assertLess(rt.index('capture_attachment(msg,'),rt.index('if key in dedup or message_id in batch_msg_ids:',rt.index('capture_attachment(msg,')))

    def test_end_to_end_private_save_dedup_and_no_reprocessing(self):
        self.add('a');self.add('b')
        report=w.process(self.q,self.s,self.pdf,max_file=1024)
        self.assertEqual(report['states'],{'saved':2})
        self.assertEqual(self.s.uploads,1);self.assertEqual(len(self.s.rows),2)
        self.assertEqual(report['saved_unique_bytes'],len(b'%PDF-1.7\nfixture'))
        self.assertFalse(list(self.q.root.glob('*.media')))
        w.process(self.q,self.s,lambda *a:self.fail('already saved'),max_file=1024)

    def test_retry_preserves_download_and_resumes_without_source_fetch(self):
        ident=self.add();self.s.fails=1
        w.process(self.q,self.s,self.pdf,max_file=1024)
        self.assertEqual(self.row(ident)['state'],'retry')
        self.assertNotIn('token',self.row(ident)['error'])
        self.q.update(ident,next_at=0)
        w.process(self.q,self.s,lambda *a:self.fail('must reuse spool'),max_file=1024)
        self.assertEqual(self.row(ident)['state'],'saved')

    def test_metadata_failure_retries_after_upload_without_losing_source(self):
        ident=self.add();real=self.s.metadata
        self.s.metadata=lambda *a:(_ for _ in ()).throw(RuntimeError())
        w.process(self.q,self.s,self.pdf,max_file=1024)
        self.assertEqual(self.row(ident)['state'],'retry');self.assertTrue((self.q.root/(ident+'.media')).exists())
        self.q.update(ident,next_at=0);self.s.metadata=real
        w.process(self.q,self.s,lambda *a:self.fail(),max_file=1024)
        self.assertEqual(self.row(ident)['state'],'saved');self.assertEqual(self.s.uploads,1)

    def test_budget_size_and_unavailable_usage_fail_closed(self):
        ident=self.add(metadata={'FILE_SIZE':'5000'})
        w.process(self.q,self.s,lambda *a:self.fail(),max_file=1000)
        self.assertEqual(self.row(ident)['state'],'held')
        other=self.add('2');self.s.usage_bytes=900
        w.process(self.q,self.s,lambda *a:self.fail(),max_file=1000,budget=1000)
        self.assertEqual(self.row(other)['error'],'storage_budget')
        third=self.add('3');self.s.usage=lambda:(_ for _ in ()).throw(RuntimeError())
        w.process(self.q,self.s,lambda *a:self.fail(),max_file=1000)
        self.assertEqual(self.row(third)['state'],'retry')

    def test_html_and_expired_responses_not_reported_as_saved(self):
        ident=self.add()
        w.process(self.q,self.s,lambda j,p,n:p.write_bytes(b'<!DOCTYPE html>login'),max_file=1024)
        self.assertEqual(self.row(ident)['state'],'invalid')
        second=self.add('2')
        def expired(*a):raise w.Failure('source_unavailable','expired')
        w.process(self.q,self.s,expired,max_file=1024)
        self.assertEqual(self.row(second)['state'],'expired')
        self.assertEqual(len(self.s.rows),0)

    def test_video_and_audio_are_archived_without_ai_or_transcoding(self):
        for ident,ct in [('v',2),('a',3)]:self.add(ident,ct)
        def raw(j,p,n):p.write_bytes(b'\x00\x00\x00\x18ftypisomfixture' if j['kind']=='video' else b'OggSfixture')
        report=w.process(self.q,self.s,raw,max_file=1024)
        self.assertEqual(report['states'],{'saved':2})
        self.assertEqual({r[0] for r in self.q.db.execute('select mime from jobs')},{'video/mp4','audio/ogg'})

    def test_initial_backfill_is_not_extrapolated_as_daily_growth(self):
        self.add('backfill');self.add('daily',cohort='daily')
        def unique(j,p,n):p.write_bytes(b'%PDF-'+j['message_id'].encode())
        w.process(self.q,self.s,unique,max_file=1024)
        self.assertIsNone(self.q.report()['projected_monthly_bytes'])
        with self.q.db:self.q.db.execute("UPDATE jobs SET created_at=? WHERE cohort='daily'",(time.time()-3*86400,))
        report=self.q.report();self.assertEqual(report['daily_last30_unique_bytes'],len(b'%PDF-daily'))
        self.assertEqual(report['backfill_unique_bytes'],len(b'%PDF-backfill'))

    def test_private_spool_and_invalid_identity(self):
        with self.assertRaises(ValueError):Queue(Path(self.temp.name)/'OneDrive'/'spool')
        with self.assertRaises(ValueError):self.add('../escape')
        self.assertEqual(self.q.path.stat().st_mode&0o777,0o600)
        with self.assertRaises(ValueError):Queue(Path.home())
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/'unrelated.txt').write_text('keep')
            with self.assertRaises(ValueError):Queue(root)

    def test_recent_poll_does_not_wait_for_historical_catchup(self):
        from types import SimpleNamespace
        route=SimpleNamespace(rid='route',square_chat_mid='room')
        helper=SimpleNamespace(_parse_routes=lambda p:[route],_get=lambda c,m,k,f:m.get(k),
          _best_message_from_event=lambda c,e:e,_extract_events=lambda c,r:r['events'],
          _extract_tokens=lambda c,r,s,t:(r.get('sync',s),r.get('cont','')),
          _extract_thread_mids_from_event=lambda *a:[],_is_thread_deleted_error=lambda e:False)
        calls=[];recent_count=[0]
        def fetch(c,room,thread,sync='',cont=''):
            calls.append((sync,cont))
            if not sync and not cont:
                recent_count[0]+=1
                return {'events':[{'id':'new'+str(recent_count[0]),'contentType':1}], 'sync':'recent','cont':'history'}
            return {'events':[{'id':'old','contentType':14}],'sync':'history-sync','cont':'next'}
        with patch.dict(sys.modules,{'chrline_open_chat_to_md':helper}),patch.object(w,'fetch_recent',fetch):
            w.scan(None,self.q,Path('unused'),pages=1)
            w.scan(None,self.q,Path('unused'),pages=0)
        self.assertEqual(calls,[('',''),('recent','history'),('','')])
        rows={r['message_id']:r['cohort'] for r in self.q.db.execute('select * from jobs')}
        self.assertEqual(rows,{'new1':'backfill','old':'backfill','new2':'daily'})

    def test_history_empty_page_completes_without_endless_refetch(self):
        from types import SimpleNamespace
        route=SimpleNamespace(rid='r',square_chat_mid='room')
        helper=SimpleNamespace(_parse_routes=lambda p:[route],_get=lambda c,m,k,f:m.get(k),
          _best_message_from_event=lambda c,e:e,_extract_events=lambda c,r:[],
          _extract_tokens=lambda c,r,s,t:('sync','stale-continuation'),
          _extract_thread_mids_from_event=lambda *a:[],_is_thread_deleted_error=lambda e:False)
        with patch.dict(sys.modules,{'chrline_open_chat_to_md':helper}),patch.object(w,'fetch_recent',return_value={}) as fetch:
            result=w.scan(None,self.q,Path('unused'),pages=10)
        self.assertEqual(fetch.call_count,1);self.assertEqual(result['pages_remaining'],0)

    def test_daily_forward_gap_is_resumed_independently_of_changing_text_anchor(self):
        from types import SimpleNamespace
        route=SimpleNamespace(rid='r',square_chat_mid='room');calls=[]
        def forward(c,**kw):
            calls.append((kw['sync_token'],kw['cont_token']))
            return {'events':[{'id':'daily'+str(len(calls)),'contentType':1}],
              'sync':'advanced','cont':'pending' if len(calls)==1 else ''}
        helper=SimpleNamespace(_parse_routes=lambda p:[route],_get=lambda c,m,k,f:m.get(k),
          _best_message_from_event=lambda c,e:e,_extract_events=lambda c,r:r['events'],
          _extract_tokens=lambda c,r,s,t:(r.get('sync',s),r.get('cont','')),
          _extract_thread_mids_from_event=lambda *a:[],_is_thread_deleted_error=lambda e:False,
          _fetch_square_chat_events=forward)
        with tempfile.TemporaryDirectory() as root:
            anchor=Path(root)/'text-state.json';anchor.write_text(json.dumps({'streams':{'room::main':{'sync_token':'anchor1'}}}))
            with patch.dict(sys.modules,{'chrline_open_chat_to_md':helper}),patch.object(w,'fetch_recent',return_value={'events':[],'sync':'history','cont':''}):
                w.scan(None,self.q,Path('unused'),pages=1,text_state=anchor)
                anchor.write_text(json.dumps({'streams':{'room::main':{'sync_token':'anchor2'}}}))
                w.scan(None,self.q,Path('unused'),pages=1,text_state=anchor)
                w.scan(None,self.q,Path('unused'),pages=1,text_state=anchor)
        self.assertEqual(calls,[('anchor1',''),('advanced','pending')])
        self.assertEqual(len(self.q.due()),2)

class Response:
    def __init__(self,status=200,data=None,headers=None,body=b''):
        self.status_code=status;self.ok=200<=status<300;self.data=data;self.headers=headers or {};self.body=body
    def json(self):return self.data
    def iter_content(self,size):
        for start in range(0,len(self.body),size):yield self.body[start:start+size]
    def close(self):pass

class TransportTest(unittest.TestCase):
    def test_bounded_source_download_uses_existing_auth_and_never_follows_redirect(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'part'
            class Client:
                Hraders4Obs={'X-Line-Access':'encrypted-fixture'}
                authToken='fixture-secret'
            class HTTP:
                def get(self,url,**kw):
                    self.url=url
                    self.kw=kw;return Response(body=b'x'*11)
            http=HTTP()
            with self.assertRaises(w.Failure):w.download(Client(),{'message_id':'123'},path,10,session=http)
            self.assertFalse(path.exists());self.assertIs(http.kw['allow_redirects'],False)
            self.assertEqual(http.kw['headers']['X-Line-Access'],'fixture-secret')
            self.assertEqual(http.url,'https://obs.line-apps.com/r/g2/m/123')

    def test_tus_resume_large_video_and_integrity(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'SUPABASE_URL':w.PROJECT,'SUPABASE_SERVICE_ROLE_KEY':'fixture'}):
            q=Queue(root);ident=q.enqueue(room_id='m',message_id='1',content_type=2)
            file=q.root/(ident+'.media');file.write_bytes(b'\0\0\0\x18ftypisom'+b'v'*(w.CHUNK+100))
            upload_url=w.STORAGE+'/storage/v1/upload/resumable/fixture'
            class HTTP:
                def __init__(self):self.data=b'';self.complete=False;self.fail=True;self.starts=[]
                def request(self,method,url,**kw):
                    if method=='GET':return Response(body=self.data) if self.complete else Response(404)
                    if method=='POST':return Response(201,headers={'Location':upload_url})
                    if method=='HEAD':return Response(headers={'Upload-Offset':str(len(self.data))})
                    if method=='PATCH':
                        self.starts.append(int(kw['headers']['Upload-Offset']))
                        if len(self.data) and self.fail:self.fail=False;return Response(503)
                        self.data+=kw['data'];self.complete=len(self.data)==file.stat().st_size
                        return Response(204,headers={'Upload-Offset':str(len(self.data))})
                    raise AssertionError(method)
            http=HTTP();s=w.Store(http);job=q.due()[0];job['mime']='video/mp4'
            with self.assertRaises(w.Failure):s.upload(q,job,file)
            job=dict(q.db.execute('SELECT * FROM jobs').fetchone());job['mime']='video/mp4'
            path,sha=s.upload(q,job,file)
            self.assertEqual(path,'objects/'+w.checksum(file));self.assertEqual(sha,w.checksum(file))
            self.assertEqual(http.starts,[0,w.CHUNK,w.CHUNK]);self.assertEqual(http.data,file.read_bytes());q.close()

    def test_wrong_project_public_bucket_unknown_usage_and_redirects_are_rejected(self):
        with patch.dict(os.environ,{'SUPABASE_URL':'https://wrong.example','SUPABASE_SERVICE_ROLE_KEY':'fixture'}):
            with self.assertRaises(ValueError):w.Store()
        with patch.dict(os.environ,{'SUPABASE_URL':w.PROJECT,'SUPABASE_SERVICE_ROLE_KEY':'fixture'}):
            s=w.Store()
            for url in ['https://evil.example/storage/v1/upload/resumable/x',w.STORAGE+'/storage/v1/upload/resumable/x?token=secret']:
                with self.assertRaises(w.Failure):s.valid_upload_url(url)
            s.request=lambda *a,**k:Response(data={'id':w.BUCKET,'public':True})
            with self.assertRaises(w.Failure):s.check_private()
            s.request=lambda *a,**k:Response(data=None)
            with self.assertRaises(w.Failure):s.usage()

class DailyRuntimeTest(unittest.TestCase):
    def test_wrapper_restores_watcher_and_filters_unexpected_child_output(self):
        from types import SimpleNamespace
        import io
        sp=importlib.util.spec_from_file_location('daily_runtime',ROOT/'scripts/jarvis_openchat_daily_runtime.py')
        daily=importlib.util.module_from_spec(sp);sp.loader.exec_module(daily)
        calls=[]
        def run(args,**kw):
            calls.append(args)
            if args[:2]==['pgrep','-f']:return SimpleNamespace(returncode=0 if args[2]=='chrline_open_chat_realtime_watch.py' else 1)
            return SimpleNamespace(returncode=0,stdout='{"states":{"saved":2},"authToken":"must-not-persist"}\n',stderr='')
        with tempfile.TemporaryDirectory() as root,patch.object(daily.Path,'home',return_value=Path(root)),patch.object(daily.subprocess,'run',side_effect=run),patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['daily','--repo-root',root,'--code-root',root,'--attachments-only']),patch('sys.stdout',io.StringIO()):
            self.assertEqual(daily.main(),0)
            result=json.loads((Path(root)/'.local/share/jarvis/openchat-ops/daily_health.json').read_text())
            self.assertEqual(result['states'],{'saved':2});self.assertTrue(result['watch_running'])
            self.assertNotIn('authToken',result)
        self.assertTrue(any('open_chat_watch_resume.sh' in str(args) for args in calls))

if __name__=='__main__':unittest.main()
