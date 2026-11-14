"""Phase 3: exact numeric readback, proof freshness and failure consistency. Offline."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import jarvis_asset_618_evidence as ev
import jarvis_asset_618_readback as rb
import jarvis_purchase_asset_evidence as capture
import jarvis_liquidity_weekly as liquidity

OWNER='11111111-1111-4111-8111-111111111111'
RUN='22222222-2222-4222-8222-222222222222'

class Query:
    def __init__(self,client,name):self.client,self.name,self.filters,self.mode,self.row=client,name,{},'read',None
    def select(self,*a,**k):return self
    def eq(self,k,v):self.filters[k]=v;return self
    def limit(self,*a):return self
    def upsert(self,row,**k):self.row=row;self.mode='write';return self
    def execute(self):
        if self.mode=='write':self.client.numeric[self.name]=deepcopy(self.row);return SimpleNamespace(data=[self.row])
        if self.name=='asset_evidence_owners': rows=[{'user_id':OWNER}]
        elif self.name=='asset_evidence_latest': rows=[deepcopy(self.client.meta)] if self.client.meta else []
        else:rows=[self.client.numeric[self.name]] if self.name in self.client.numeric else []
        return SimpleNamespace(data=[r for r in rows if all(r.get(k)==v for k,v in self.filters.items())])
class Fake:
    def __init__(self):self.meta=None;self.blobs={};self.numeric={};self.fail=None;self.storage=self;self.uploads=0
    def get_bucket(self,name):return {"public":False}
    def table(self,name):return Query(self,name)
    def from_(self,name):assert name==ev.BUCKET;return self
    def upload(self,path,data,options):
        self.uploads+=1
        if self.fail=='upload':raise RuntimeError('secret')
        self.blobs[path]=data
    def download(self,path):return b'corrupt' if self.fail=='download' else self.blobs[path]
    def rpc(self,name,args):
        def execute():
            if name=='asset_evidence_begin':
                if self.fail=='begin':raise RuntimeError('secret')
                if not self.meta:self.meta={'id':str(uuid.uuid4()),'owner_id':OWNER,'storage_path':None,'active_slot':None,'captured_at':None}
                if self.meta.get('last_attempt_status')=='pending':raise RuntimeError('pending')
                self.coords={'account_scope':args['p_scope'],'account_id':args['p_account'],'contract_key':args['p_contract'],'view_key':args['p_view']}
                self.meta.update(self.coords,last_attempt_id=args['p_attempt'],last_attempt_status='pending')
            elif name=='asset_evidence_commit':
                if self.fail=='commit':raise RuntimeError('secret')
                slot='b' if self.meta['active_slot']=='a' else 'a'
                self.meta.update(storage_path=ev.slot_path(OWNER,self.coords,slot),active_slot=slot,sha256=args['p_sha'],captured_at=args['p_captured'],source_as_of=args['p_asof'],run_id=args['p_run'],last_attempt_status='ok')
            elif name=='asset_evidence_fail':
                if self.meta.get('last_attempt_status')=='pending':self.meta['last_attempt_status']='failed'
            return SimpleNamespace(data=deepcopy(self.meta))
        return SimpleNamespace(execute=execute)

class NumericTests(unittest.TestCase):
    def setUp(self):self.row={'account_id':'sbi_index','as_of':'2026-11-14','value_jpy':'123.00','source':'weekly_web'};self.c=Fake();self.c.numeric['portfolio_snapshots']=deepcopy(self.row)
    def test_exact_readback_and_unknown_source_date(self):
        check=rb.verify_snapshot(self.c,'portfolio_snapshots',self.row)
        self.assertEqual(check['status'],'verified');self.assertFalse(check['source_as_of_verified'])
    def test_changed_balance_rejected(self):
        self.c.numeric['portfolio_snapshots']['value_jpy']=124
        with self.assertRaises(rb.ReadbackError):rb.verify_snapshot(self.c,'portfolio_snapshots',self.row)
    def test_missing_wrong_date_or_source_rejected(self):
        for field,value in [('as_of','2026-11-13'),('source','manual')]:
            self.c.numeric['portfolio_snapshots']={**self.row,field:value}
            with self.assertRaises(rb.ReadbackError):rb.verify_snapshot(self.c,'portfolio_snapshots',self.row)
    def test_cost_mismatch_rejected(self):
        with self.assertRaises(rb.ReadbackError):rb.verify_snapshot(self.c,'portfolio_snapshots',{**self.row,'cost_jpy':200})
    def test_invalid_number_and_date(self):
        for v in [True,None,'NaN','Infinity']:
            with self.assertRaises(rb.ReadbackError):rb.decimal_text(v)
        with self.assertRaises(rb.ReadbackError):rb.row_digest('portfolio_snapshots',{**self.row,'as_of':'2026-02-30'})
    def test_canonical_amounts_and_digest(self):
        for v in ('123',123,123.0,'00123.000'):
            self.assertEqual(rb.row_digest('portfolio_snapshots',{**self.row,'value_jpy':v}),rb.row_digest('portfolio_snapshots',self.row))
    def test_liquidity_readback_is_not_count_only(self):
        checks={};self.assertEqual(liquidity.upsert_liquidity(self.c,[{'account_id':'wallet','balance_jpy':12,'zaim_name':'fixture'}],'2026-11-14',readbacks=checks),1)
        self.assertEqual(checks['wallet']['status'],'verified');self.assertFalse(checks['wallet']['source_as_of_verified'])

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'proof.png'
        start=datetime.now(timezone.utc).isoformat();Image.new('RGB',(200,100),'white').save(self.path)
        self.receipt=ev.capture_receipt(self.path,run_id=RUN,step='axa',started_at=start,finished_at=datetime.now(timezone.utc).isoformat(),fresh_screen=True)
        self.item={'account_scope':'portfolio','account_id':'sbi_index','contract_key':'primary','view_key':'balance','source_as_of':(date.today()-timedelta(days=1)).isoformat(),'reviewed_by':'owner','validation':{k:True for k in ('normal_page','account_match','contract_match','source_date_match')}}
    def test_valid_reviewed_image(self):self.assertEqual(ev.reviewed_artifact(self.receipt,self.item)[1]['sha256'],self.receipt['sha256'])
    def test_old_file_cannot_receive_fresh_receipt(self):
        past=(datetime.now(timezone.utc)-timedelta(days=1)).timestamp();os.utime(self.path,(past,past))
        with self.assertRaises(ev.Blocked):ev.capture_receipt(self.path,run_id=RUN,step='axa',started_at=self.receipt['started_at'],finished_at=datetime.now(timezone.utc).isoformat(),fresh_screen=True)
    def test_reference_note_not_eligible(self):
        with self.assertRaisesRegex(ev.Blocked,'reference_is_not_screen_proof'):ev.reviewed_artifact({**self.receipt,'candidate_type':'derived_reference'},self.item)
    def test_unreviewed_identity_or_date_is_held(self):
        for flag in self.item['validation']:
            item=deepcopy(self.item);item['validation'][flag]=False
            with self.assertRaises(ev.Blocked):ev.reviewed_artifact(self.receipt,item)
    def test_changed_bytes_or_mtime_rejected(self):
        self.path.write_bytes(self.path.read_bytes()+b'changed')
        with self.assertRaises(ev.Blocked):ev.reviewed_artifact(self.receipt,self.item)
    def test_future_source_date_rejected(self):
        with self.assertRaises(ev.Blocked):ev.reviewed_artifact(self.receipt,{**self.item,'source_as_of':'2099-01-01'})
    def test_corrupt_and_oversize_image_rejected(self):
        self.path.write_text('not a PNG')
        with self.assertRaises(ev.Blocked):ev.png_bytes(self.path)
        with patch.object(ev,'MAX_BYTES',1):
            with self.assertRaises(ev.Blocked):ev.png_bytes(self.path)
    def test_symlink_rejected(self):
        link=Path(self.tmp.name)/'link.png';link.symlink_to(self.path)
        with self.assertRaises(ev.Blocked):ev.png_bytes(link)
    def test_paths_cannot_contain_account_numbers_or_traversal(self):
        with self.assertRaises(ev.Blocked):ev.coordinates({**self.item,'contract_key':'../secret'})
        with self.assertRaises(ev.Blocked):ev.slot_path(OWNER,self.item,'unknown')
    def test_publish_after_upload_and_independent_readbacks(self):
        c=Fake();s=ev.EvidenceStore(c,OWNER);s.check_owner()
        self.assertEqual(s.publish(self.item,self.receipt,RUN)['status'],'ok')
        self.assertEqual(c.meta['sha256'],self.receipt['sha256']);self.assertEqual(c.uploads,1)
    def test_all_failures_leave_prior_normal_pointer(self):
        for failure in ('upload','download','commit'):
            c=Fake();c.meta={'id':str(uuid.uuid4()),'owner_id':OWNER,'storage_path':'previous-good','active_slot':'a','sha256':'old','captured_at':'2020-01-01T00:00:00+00:00','source_as_of':'2020-01-01'};c.fail=failure
            result=ev.EvidenceStore(c,OWNER).publish(self.item,self.receipt,RUN)
            self.assertEqual(result['status'],'error',failure);self.assertEqual(c.meta['storage_path'],'previous-good');self.assertEqual(c.meta['sha256'],'old');self.assertEqual(c.meta['last_attempt_status'],'failed')
            self.assertNotIn('secret',json.dumps(result))
    def test_invalid_review_never_uploads(self):
        c=Fake();item={**self.item,'validation':{}}
        self.assertEqual(ev.EvidenceStore(c,OWNER).publish(item,self.receipt,RUN)['status'],'error');self.assertEqual(c.uploads,0)
    def test_fresh_copy_requires_this_invocation(self):
        with patch.object(capture,'CAPTURE_STARTED',datetime.now(timezone.utc).isoformat()):
            with self.assertRaises(ev.Blocked):capture._copy_fresh(self.path,Path(self.tmp.name)/'copy.png','axa')
    def test_collector_failure_cannot_use_old_debug(self):
        with patch.object(capture.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='',stderr='secret')):
            with self.assertRaisesRegex(ev.Blocked,'collector_failed_no_old_image_fallback'):capture._run_collector(Path('/fake.py'))
    def test_otp_pause_exit_zero_is_not_success(self):
        with patch.object(capture.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='OTP paused',stderr='')):
            with self.assertRaises(ev.Blocked):capture._run_collector(Path('/fake.py'))
    def test_public_bucket_is_never_used(self):
        c=Fake();c.get_bucket=lambda name:{'public':True}
        with self.assertRaises(ev.Blocked):ev.EvidenceStore(c,OWNER).publish(self.item,self.receipt,RUN)
        self.assertEqual(c.uploads,0)
    def test_owner_must_be_explicitly_enrolled(self):
        with self.assertRaises(ev.Blocked):ev.EvidenceStore(Fake(),'33333333-3333-4333-8333-333333333333').check_owner()

class ReportTests(unittest.TestCase):
    def setUp(self):
        import jarvis_asset_618_report as report
        self.report = report
        self.now = datetime(2026,11,14,3,tzinfo=timezone.utc)
        self.check = {'status':'verified','record_as_of':'2026-11-14','row_digest':'a'*64,'checked_at':'2026-11-14T02:00:00Z'}
        self.checks = {'portfolio_snapshots':{'sbi_index':self.check}}
        self.state = {'finished_at':'2026-11-14T02:01:00Z','iso_week':'2026-W46','sources':{'sbi_index':{'status':'ok'}},'asset_618':{'run_id':RUN,'numeric_readbacks':self.checks}}
    def test_old_metadata_never_implies_display_confirmation(self):
        result=self.report.build_report(self.state,now=self.now)
        self.assertEqual(result['current_write'],'readback_recorded')
        self.assertEqual(result['kurashift_display'],'not_verified')
    def test_only_matching_display_receipt_counts(self):
        receipt={'numeric_digest':rb.context_digest(self.checks),'matched_count':1,'unresolved_count':2,'checked_at':'2026-11-14T02:02:00Z'}
        result=self.report.build_report(self.state,{'display_check':receipt},now=self.now)
        self.assertEqual(result['kurashift_display'],'checked_for_run')
        self.assertIn('未確認2件',result['drafts']['report'])
        receipt['numeric_digest']='b'*64
        self.assertEqual(self.report.build_report(self.state,{'display_check':receipt},now=self.now)['kurashift_display'],'not_verified')
    def test_image_success_and_failure_are_separate_from_numeric(self):
        result=self.report.build_report(self.state,now=self.now,image_run={'kind':'evidence_publish','image_results':[{'status':'ok'},{'status':'error'}]})
        self.assertEqual(result['image_result'],{'updated':1,'failed':1})
        self.assertIn('画像更新：1件／失敗1件',result['drafts']['report'])
    def test_future_readback_is_not_verified(self):
        self.check['checked_at']='2099-01-01T00:00:00Z'
        self.assertEqual(self.report.build_report(self.state,now=self.now)['numeric_readback']['verified'],0)

if __name__=='__main__':unittest.main()
