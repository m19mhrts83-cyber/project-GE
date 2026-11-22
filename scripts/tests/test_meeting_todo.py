"""Synthetic only: no network, private state or real notifications."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import jarvis_meeting_todo as m
import jarvis_meeting_minutes_curate as curate

# Do not read a developer's private aliases in any test/CI process.
_policy_patch = None
def setUpModule():
    global _policy_patch
    _policy_patch = patch.object(m,'load_owner_policy',return_value={
        'version':1,'configured':True,'owner_aliases':['owner-alias','owner-alt'],
        'other_aliases':[],'meetings':{}})
    _policy_patch.start()

def tearDownModule():
    _policy_patch.stop()

class Store:
    def __init__(self):self.rows={}
    def get(self,k):return self.rows.get(k)
    def insert(self,k,v):self.rows.setdefault(k,json.dumps(v,ensure_ascii=False))
    def cas(self,k,old,v):
        if self.rows.get(k)!=old:return False
        self.rows[k]=json.dumps(v,ensure_ascii=False);return True

def artifact(mid='meeting-A',assignee='owner-alias',todo='Check synthetic input'):
    return m.prepared({'meeting_id':mid,'extracted':True,'body':'# Title\n## ひとことで\na\n## 決まったこと\nb\n## ToDo\nc\n## 次回\nd',
        'candidates':[{'todo':todo,'assignee':assignee,'evidence':'explicit action assignment'}]},mid)

class CandidateTests(unittest.TestCase):
    def test_stable_id_before_truncation(self):
        a=m.candidate('m',{'todo':'Check  input','assignee':'owner-alias','evidence':'x'})
        b=m.candidate('m',{'todo':'Check input','assignee':'owner-alt','evidence':'y'})
        self.assertEqual(a['candidate_id'],b['candidate_id'])
        self.assertNotEqual(a['candidate_id'],m.candidate('other',{'todo':'Check input','assignee':'owner-alias','evidence':'x'})['candidate_id'])
        self.assertNotEqual(m.candidate('m',{'todo':'a'*210+'b','evidence':'x'})['candidate_id'],m.candidate('m',{'todo':'a'*210+'c','evidence':'x'})['candidate_id'])
    def test_unknown_owner_and_dates(self):
        c=m.candidate('m',{'todo':'task','assignee':'','evidence':'x','due_raw':'tomorrow','due_date':'2026-11-23'})
        self.assertEqual(c['status'],'held');self.assertIsNone(c['due_date'])
        with self.assertRaises(ValueError):m.candidate('m',{'todo':'task'})
    def test_empty_extraction_is_explicit(self):
        a=artifact();a['candidates']=[]
        self.assertEqual(m.prepared(a,'meeting-A')['candidates'],[])
        with self.assertRaises(ValueError):m.prepared({'meeting_id':'x'},'x')
    def test_localized_action_section(self):
        rows=m.extract_only({'id':'m','summary':'## 5. アクションアイテム\n- **owner-alias**: Check input\n- **other**: Another task\n## Next\n- irrelevant'})
        self.assertEqual(len(rows),2);self.assertEqual(sum(c['owner_confirmed'] for c in rows),1)

class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'outbox.json';self.store=Store();self.posts=[]
    def tearDown(self):self.tmp.cleanup()
    def queue(self,mid='meeting-A',assignee='owner-alias'):
        m.enqueue(artifact(mid,assignee),{'page_id':'page','notion_url':'https://example.test/note'},self.path)
    def test_unsaved_is_never_enqueued(self):
        with self.assertRaises(ValueError):m.enqueue(artifact(),{},self.path)
        self.assertFalse(self.path.exists())
    def test_multimeeting_no_reextract_terminal_no_reproposal(self):
        self.queue();self.queue('meeting-B');self.queue('meeting-C','unknown')
        with patch('jarvis_todoist_sb_propose._fetch_meeting_summary',side_effect=AssertionError('re-extraction')):
            r=m.dispatch(self.store,lambda p:self.posts.append(p) or 0,self.path)
        self.assertEqual(r,{'posted':2,'held':1});self.assertEqual(len(self.posts),2)
        for cid,raw in self.store.rows.items():
            row=json.loads(raw);row['status']='dismissed';self.store.rows[cid]=json.dumps(row)
        self.queue()
        self.assertEqual(m.dispatch(self.store,lambda p:self.posts.append(p) or 0,self.path)['posted'],0)
        self.assertEqual(len(self.posts),2)
    def test_uncertain_post_never_auto_reposts(self):
        self.queue()
        with self.assertRaises(RuntimeError):m.dispatch(self.store,lambda p:1,self.path)
        self.assertEqual(m.dispatch(self.store,lambda p:self.posts.append(p) or 0,self.path)['posted'],0)
        self.assertFalse(self.posts)
    def test_limit_keeps_unsent(self):
        for i in range(4):self.queue(str(i))
        self.assertEqual(m.dispatch(self.store,lambda p:0,self.path,limit=3)['posted'],3)
        self.assertEqual(m.dispatch(self.store,lambda p:0,self.path,limit=3)['posted'],1)
    def test_recover_ignores_legacy_six(self):
        with patch.object(curate,'_load_state',return_value={'saved':{str(i):{'page_id':'old'} for i in range(6)}}),patch.object(m,'dispatch',return_value={'posted':0}) as d,patch.object(m,'enqueue') as q:
            curate.cmd_recover(None);q.assert_not_called();d.assert_called_once()
    def test_prepare_is_no_network(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('network')):
            a=artifact();m.atomic_json(self.path,a);self.assertEqual(m.load_json(self.path)['meeting_id'],'meeting-A')

class ApplyTests(unittest.TestCase):
    def setup_apply(self,tmp):
        state={'proposals':[{'meeting_id':'meeting-A','title':'Synthetic','created':'2026-11-22'}],'saved':{}}
        prepared=Path(tmp)/'prepared.json';m.atomic_json(prepared,artifact())
        return state,prepared
    def test_notion_failure_never_handoffs(self):
        import argparse
        with tempfile.TemporaryDirectory() as tmp:
            state,p=self.setup_apply(tmp)
            with patch.object(curate,'_load_state',return_value=state),patch.object(curate,'_load_yaml',return_value={}),patch.object(curate,'_save_state'),patch.object(curate,'_prepared_path',return_value=p),patch.object(curate,'_create_notion_page',side_effect=RuntimeError('fail')),patch.object(m,'enqueue') as q:
                with self.assertRaises(RuntimeError):curate.cmd_apply(argparse.Namespace(select='1',dry_run=False))
                q.assert_not_called()
    def test_save_durable_before_enqueue(self):
        import argparse
        with tempfile.TemporaryDirectory() as tmp:
            state,p=self.setup_apply(tmp);saved=[]
            with patch.object(curate,'_load_state',return_value=state),patch.object(curate,'_load_yaml',return_value={}),patch.object(curate,'_save_state',side_effect=lambda s:saved.append(json.loads(json.dumps(s)))),patch.object(curate,'_prepared_path',return_value=p),patch.object(curate,'_create_notion_page',return_value={'id':'p','url':'https://example.test/p'}),patch.object(m,'enqueue',side_effect=RuntimeError('offline')):
                with self.assertRaises(RuntimeError):curate.cmd_apply(argparse.Namespace(select='1',dry_run=False))
                self.assertEqual(saved[-1]['saved']['meeting-A']['page_id'],'p')

class RegressionTests(unittest.TestCase):
    def test_legacy_digest_skips_prepared_meeting_without_extracting(self):
        import jarvis_todoist_312_digest as digest
        import jarvis_todoist_sb_propose as sb
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'prepared';p.write_text('{}')
            with patch.object(sb,'_list_or_search',return_value=[{'id':'m'}]),patch.object(curate,'_prepared_path',return_value=p),patch.object(digest,'_run_json',side_effect=AssertionError('re-extraction')):
                self.assertEqual(digest._collect_sb(mine_only=True),[])
    def test_long_body_not_truncated(self):
        requests=[]
        with patch.object(curate,'_notion_token',return_value='fake'),patch.object(curate,'_notion_req',side_effect=lambda *a:requests.append(a) or {'id':'p'}):
            curate._create_notion_page(title='Synthetic',body='x'*4500,meeting_id='m',project_url='',cfg={'inbox_page_id':'x'})
        children=requests[0][2]['children']
        total=''.join(b[b['type']]['rich_text'][0]['text']['content'] for b in children[1:])
        self.assertEqual(len(total),4500)
    def test_corrupt_state_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'state';p.write_text('{broken')
            with patch.object(curate,'STATE_PATH',p):
                with self.assertRaises(RuntimeError):curate._load_state()

class StoreVersionTests(unittest.TestCase):
    def test_long_value_uses_small_monotonic_version_not_query_body(self):
        row={'candidate_id':'a'*64,'evidence':'x'*20000,'status':'posted'}
        raw=json.dumps(row)
        with patch.dict('os.environ',{'JARVIS_SUPABASE_URL':'https://example.test','JARVIS_SUPABASE_SERVICE_ROLE_KEY':'synthetic'}):
            s=m.Store()
        requests=[]
        def fake(method,params,body=None,prefer=None):
            requests.append((method,params,body))
            if method=='GET':return [{'value':raw,'updated_at':'2026-11-22T00:00:00+00:00'}]
            return [{'key':'k'}]
        s.request=fake
        self.assertEqual(s.get('a'*64),raw)
        self.assertTrue(s.cas('a'*64,raw,{**row,'status':'creating'}))
        self.assertNotIn('value',requests[-1][1]);self.assertIn('updated_at',requests[-1][1])
        self.assertFalse(s.cas('a'*64,raw,{**row,'status':'dismissed'}))
    def test_prepared_meeting_cannot_change_after_save(self):
        import argparse
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json';m.atomic_json(p,artifact())
            with patch.object(curate,'_load_state',return_value={'saved':{'meeting-A':{}}}):
                with self.assertRaises(ValueError):curate.cmd_prepare(argparse.Namespace(file=str(p)))

class DirectProposalRegression(unittest.TestCase):
    def test_legacy_cli_never_reextracts_a_prepared_714_meeting(self):
        import argparse
        import jarvis_todoist_sb_propose as sb
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'prepared';p.write_text('{}')
            with patch.object(sb,'_load_yaml_signals',return_value={}),patch.object(curate,'_prepared_path',return_value=p),patch.object(sb,'_fetch_meeting_summary',side_effect=AssertionError('re-extraction')),patch.object(sb,'_save_state',side_effect=AssertionError('state overwrite')):
                self.assertEqual(sb.cmd_propose(argparse.Namespace(meeting_id='m',json=True)),0)

class CardTests(unittest.TestCase):
    def test_meeting_card_has_no_legacy_number_reply_and_keeps_stable_id(self):
        import base64
        import jarvis_todoist_312_slack_blocks as blocks
        cid='a'*64
        it={'n':1,'title':'Synthetic','lane':'ai_raimo','candidate_id':cid}
        payload=blocks.build_create_blocks([it],header_text='312',fallback_text='test',url_mode=False)
        self.assertNotIn('起票して N',json.dumps(payload,ensure_ascii=False))
        self.assertIn('次: 人判断のみ',payload['blocks'][-1]['elements'][0]['text'])
        encoded=blocks.encode_proposal(it)
        self.assertEqual(json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))['candidate_id'],cid)
    def test_missing_signing_key_never_writes_production_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'outbox';m.enqueue(artifact(),{'page_id':'p','notion_url':'https://example.test/n'},p)
            with patch('jarvis_todoist_312_slack_blocks._action_secret',return_value=''),patch.object(m,'Store',side_effect=AssertionError('store write')):
                with self.assertRaises(RuntimeError):m.dispatch(path=p)
