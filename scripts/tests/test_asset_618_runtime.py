"""618 Phase 2 safety and wiring tests, no live services or financial logins."""
import contextlib
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_asset_618_runtime as rt
import jarvis_portfolio_weekly as weekly
import jarvis_purchase_asset_evidence as evidence
import jarvis_kurashift_job_worker as worker

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)

def decision(rid=1, action='rule_accept', effect='exclude_target', key='rule', **spec):
    data = {'action': action, 'owner_confirmed': True, 'idem_key': 'decision-'+str(rid),
            'choice': 'explicit choice', 'rule': {'decision_key': key, 'targets': ['sbi_index'],
            'effect': effect, 'effective_from': '2026-11-01T00:00:00+00:00', **spec}}
    return {'id': rid, **rt.prepare_decision(data)}

def resolve(rows, **kw):
    return rt.resolve_decisions(rows, ['sbi_index', 'axa_life'], 'run-current', now=NOW, **kw)


class DecisionTests(unittest.TestCase):
    def test_adopted_excludes_and_records_id(self):
        p=resolve([decision()]); self.assertEqual(p['excluded_targets'], ['sbi_index']); self.assertEqual(p['applied_decision_ids'], [1])
    def test_reject_comment_never_promoted(self):
        for action in ('rule_reject','comment'):
            self.assertEqual(resolve([decision(action=action)])['applied_decision_ids'], [])
    def test_once_only_and_explicit_retry(self):
        row=decision(action='rule_once',run_id='run-prior',allow_retry=False)
        self.assertEqual(resolve([row],retry_of='run-prior')['applied_decision_ids'], [])
        row['payload']['asset_618']['allow_retry']=True
        self.assertEqual(resolve([row],retry_of='run-prior')['applied_decision_ids'], [1])
    def test_once_matching_run(self):
        self.assertEqual(resolve([decision(action='rule_once',run_id='run-current')])['applied_decision_ids'], [1])
    def test_expired_once_restores_standing(self):
        rows=[decision(),decision(2,action='rule_once',effect='include_target',run_id='run-current',expires_at='2026-11-02T00:00:00+00:00')]
        self.assertEqual(resolve(rows)['applied_decision_ids'],[1])
    def test_revision_replaces_old_target_scope(self):
        rows=[decision(),decision(2,targets=['axa_life'])]
        plan=resolve(rows)
        self.assertEqual(plan['excluded_targets'],['axa_life'])
        self.assertEqual(plan['allowed_targets'],['sbi_index'])
    def test_expired_and_future(self):
        for spec in ({'expires_at':'2026-11-02T00:00:00+00:00'}, {'effective_from':'2026-12-01T00:00:00+00:00'}):
            self.assertEqual(resolve([decision(**spec)])['applied_decision_ids'], [])
    def test_revert_does_not_resurrect_old_rule(self):
        rows=[decision(1),decision(2),decision(3,action='rule_revert',reverts_id=2)]
        self.assertEqual(resolve(rows)['applied_decision_ids'], [])
    def test_once_revert_restores_standing(self):
        rows=[decision(1),decision(2,action='rule_once',effect='include_target',run_id='run-current'),decision(3,action='rule_revert',reverts_id=2)]
        self.assertEqual(resolve(rows)['applied_decision_ids'], [1])
    def test_conflict_holds_only_affected(self):
        p=resolve([decision(),decision(2,effect='include_target',key='other')]); self.assertEqual(p['held_targets'],['sbi_index']); self.assertEqual(p['allowed_targets'],['axa_life'])
    def test_explicit_hold(self):
        self.assertEqual(resolve([decision(effect='hold_target')])['held_targets'],['sbi_index'])
    def test_bad_date_or_effect_holds(self):
        for field,value in [('effective_from','2026-11-01'),('effect','change_balance')]:
            row=decision();row['payload']['asset_618'][field]=value
            self.assertEqual(resolve([row])['held_targets'],['sbi_index'])
    def test_unconfirmed_never_adopted(self):
        row=decision();row['payload']['asset_618']['owner_confirmed']=False
        self.assertEqual(resolve([row])['held_targets'],['sbi_index'])
    def test_wrong_surface_ignored(self):
        row=decision();row['surface']='other';self.assertEqual(resolve([row])['applied_decision_ids'],[])
    def test_malformed_history_is_blocked(self):
        for rows in ([{'id':'bad'}],[{**decision(),'payload':[]}],[decision(),decision()]):
            with self.assertRaises(rt.Blocked): resolve(rows)
    def test_unknown_revert_blocks(self):
        with self.assertRaises(rt.Blocked): resolve([decision(3,action='rule_revert',reverts_id=99)])
    def test_unknown_target_is_not_silently_accepted(self):
        with self.assertRaises(rt.Blocked): decision(targets=['misspelled_target'])
    def test_prepare_requires_owner_and_window(self):
        with self.assertRaises(rt.Blocked): rt.prepare_decision({'action':'rule_accept'})
        with self.assertRaises(rt.Blocked): decision(expires_at='2025-01-01T00:00:00+00:00')
    def test_repeat_preparation_is_idempotent(self):
        self.assertEqual(decision()['payload']['asset618_fingerprint'], decision()['payload']['asset618_fingerprint'])
    def test_reason_not_invented(self):
        self.assertIsNone(decision()['note'])
    def test_failed_read_sanitized(self):
        c=Mock();c.table.side_effect=RuntimeError('secret-credential')
        with self.assertRaisesRegex(rt.Blocked,'^decision_read_failed$'): rt.DecisionStore(c).read()
    def test_save_idempotent_and_conflict(self):
        c=Mock(); row=decision(); response=SimpleNamespace(data=[{'id':42,'payload':row['payload']}])
        c.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value=response
        self.assertEqual(rt.DecisionStore(c).save(row),42)
        c.table.return_value.insert.assert_not_called()
        response.data[0]['payload']={'asset618_fingerprint':'wrong'}
        with self.assertRaises(rt.Blocked): rt.DecisionStore(c).save(row)
    def test_failed_write_never_returns_success(self):
        c=Mock(); c.table.side_effect=RuntimeError('secret')
        with self.assertRaisesRegex(rt.Blocked,'^decision_not_persisted_or_key_conflict$'): rt.DecisionStore(c).save(decision())


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def test_cross_process_lock(self):
        code='import sys;sys.path.insert(0,sys.argv[1]);from jarvis_asset_618_runtime import SharedLock,Busy;from pathlib import Path\ntry:\n with SharedLock(Path(sys.argv[2])): pass\nexcept Busy: sys.exit(23)'
        with rt.SharedLock(self.root):
            result=subprocess.run([sys.executable,'-c',code,str(Path(rt.__file__).parent),str(self.root)],capture_output=True)
        self.assertEqual(result.returncode,23,result.stderr)
        with rt.SharedLock(self.root): pass
    def test_legacy_lock_is_not_removed(self):
        (self.root/'weekly.lock.d').mkdir()
        with self.assertRaises(rt.Busy):
            with rt.SharedLock(self.root): pass
        self.assertTrue((self.root/'weekly.lock.d').exists())
    def test_failed_decision_read_blocks_collection_and_releases(self):
        with patch.object(rt.DecisionStore,'read',side_effect=rt.Blocked('decision_read_failed')):
            with self.assertRaises(rt.Blocked):
                with rt.Run('weekly',['sbi_index'],root=self.root): self.fail('must not execute')
        with rt.SharedLock(self.root): pass
        row=json.loads(next((self.root/'asset618-runs').glob('*.json')).read_text());self.assertEqual(row['status'],'blocked')
    def test_exception_release_and_interrupted_retry(self):
        with patch.object(rt.DecisionStore,'read',return_value=[]):
            with self.assertRaisesRegex(RuntimeError,'boom'):
                with rt.Run('weekly',['sbi_index','axa_life'],root=self.root) as run:
                    rid=run.data['run_id'];raise RuntimeError('boom')
        with rt.SharedLock(self.root): pass
        self.assertEqual(set(rt.retry_targets(rid,'weekly',self.root)),{'sbi_index','axa_life'})
    def test_retry_omits_success_and_excluded(self):
        with patch.object(rt.DecisionStore,'read',return_value=[]):
            with rt.Run('weekly',['sbi_index','axa_life'],root=self.root) as run:
                run.record({'sbi_index':{'status':'ok'},'axa_life':{'status':'error'}})
        self.assertEqual(rt.retry_targets(run.data['run_id'],'weekly',self.root),['axa_life'])
        with self.assertRaises(rt.Blocked):rt.retry_targets(run.data['run_id'],'evidence',self.root)
    def test_reference_preserved_are_not_success(self):
        with patch.object(rt.DecisionStore,'read',return_value=[]):
            with rt.Run('weekly',['sbi_index','axa_life'],root=self.root) as run:
                run.record({'sbi_index':{'status':'ok','note':'manual'},'axa_life':{'status':'ok','note':'preserved later error'}})
        self.assertEqual(run.data['results'],{'sbi_index':'reference','axa_life':'error'})
    def test_snapshot_boundary_persists_without_end_of_run(self):
        with patch.object(rt.DecisionStore,'read',return_value=[]):
            with self.assertRaises(RuntimeError):
                with rt.Run('weekly',['sbi_index','axa_life'],root=self.root) as run:
                    client=Mock()
                    client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'account_id':'sbi_index','as_of':weekly.today_jst().isoformat(),'value_jpy':12,'source':'weekly_web'}]
                    weekly.upsert_snapshot(client,'sbi_index',12,source='weekly_web')
                    raise RuntimeError('interrupted')
        self.assertEqual(rt.retry_targets(run.data['run_id'],'weekly',self.root),['axa_life'])
    def test_snapshot_failure_is_retryable(self):
        client=Mock();client.table.side_effect=RuntimeError('failed')
        with patch.object(rt.DecisionStore,'read',return_value=[]):
            with self.assertRaises(RuntimeError):
                with rt.Run('weekly',['sbi_index'],root=self.root) as run:
                    weekly.upsert_snapshot(client,'sbi_index',12,source='weekly_web')
        self.assertEqual(rt.retry_targets(run.data['run_id'],'weekly',self.root),['sbi_index'])
    def test_duplicate_run_id_preserves_old_record(self):
        rid=str(uuid.uuid4())
        with rt.Run('weekly',['sbi_index'],preview=True,root=self.root,run_id=rid) as run: pass
        before=run.path.read_text()
        with self.assertRaises(rt.Busy):
            with rt.Run('weekly',['axa_life'],preview=True,root=self.root,run_id=rid):pass
        self.assertEqual(before,run.path.read_text())
    def test_no_sensitive_values_in_ledger(self):
        with patch.object(rt.DecisionStore,'read',return_value=[]):
            with rt.Run('weekly',['sbi_index'],root=self.root) as run:
                run.record({'sbi_index':{'status':'ok','value_jpy':987654321,'note':'secret'}})
        self.assertNotIn('987654321',run.path.read_text());self.assertNotIn('secret',run.path.read_text())


class WiringTests(unittest.TestCase):
    def test_worker_scoped_retry_args_and_conflict(self):
        rid=str(uuid.uuid4());cmd=worker.command_for('portfolio_weekly',{'retry_run':rid})
        self.assertEqual(cmd[-2:],['--retry-run',rid]);self.assertNotIn('--force',cmd)
        with self.assertRaises(ValueError):worker.command_for('portfolio_weekly',{'retry_run':rid,'force':True})
        self.assertEqual(worker.command_for('portfolio_weekly',{'target_ids':['sbi_index']})[-2:],['--only','sbi_index'])
    def test_scoped_weekly_never_calls_other_fetchers(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(rt.DecisionStore,'read',return_value=[]):
            with rt.Run('weekly',['sbi_index'],root=Path(tmp)) as run:
                run.data['restricted']=True
                args=SimpleNamespace(force=False,cloud_only=False,dry_run=False,sony_only=False)
                with contextlib.ExitStack() as stack:
                    for name in ('load_private_env','sb_client','write_review','upsert_sync_meta','save_state'):
                        stack.enter_context(patch.object(weekly,name))
                    stack.enter_context(patch.object(weekly,'load_state',return_value={'iso_week':weekly.iso_week(),'sources':{'axa_life':{'status':'ok','value_jpy':100}}}))
                    sbi=stack.enter_context(patch.object(weekly,'fetch_sbi',return_value={'status':'ok','value_jpy':12}))
                    other=[stack.enter_context(patch.object(weekly,n,side_effect=AssertionError(n))) for n in ('fetch_axa','fetch_mhi_zaim','fetch_akatsuki','fetch_bloomo','fetch_prudential_by_account','ingest_sony','fetch_tachibana')]
                    sub=stack.enter_context(patch.object(weekly.subprocess,'run',side_effect=AssertionError('subprocess')))
                    write=stack.enter_context(patch.object(weekly,'upsert_snapshot'))
                    with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(weekly._collect_main(args,run),0)
                    sbi.assert_called_once();write.assert_called_once();self.assertEqual(write.call_args.args[1],'sbi_index')
                    payload=weekly.save_state.call_args.args[0]
                    self.assertEqual(payload['sources']['axa_life']['status'],'reference');self.assertTrue(payload['partial_scope']);self.assertFalse(payload['last_full_ok'])
                    self.assertEqual(payload['asset_618']['run_id'],run.data['run_id'])
    def test_evidence_scoped_and_reference_not_fresh(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(rt.DecisionStore,'read',return_value=[]):
            with rt.Run('evidence',['sony'],root=Path(tmp)/'logs') as run:
                def capture():
                    path=Path(tmp)/'old.png'
                    from PIL import Image
                    Image.new('RGB',(100,50)).save(path)
                    evidence.RESULTS.append({'status':'ok','name':'old_debug','path':str(path),'note':'copied'})
                with patch.object(evidence,'capture_sony',side_effect=capture) as sony, patch.object(evidence,'capture_axa',side_effect=AssertionError('wrong scope')), patch.object(evidence,'_write_inventory'), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(evidence._collect_main(SimpleNamespace(out=tmp,loans_json='none',only='sony',executor='jarvis'),run),0)
                sony.assert_called_once();self.assertEqual(run.data['results']['sony'],'reference')
    def test_codex_capture_never_calls_bank_or_otp_capable_collectors(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(rt.DecisionStore,'read',return_value=[]):
            with rt.Run('evidence',['paypay','sbi_net','axa','akatsuki','sony','prudential'],root=Path(tmp)/'logs') as run:
                with contextlib.ExitStack() as stack:
                    for name in ('capture_paypay','capture_sbi_net','capture_axa','capture_akatsuki','capture_sony','capture_prudential'):
                        stack.enter_context(patch.object(evidence,name,side_effect=AssertionError('must be Jarvis')))
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(evidence._collect_main(SimpleNamespace(out=tmp,loans_json='none',only='all',executor='codex'),run),0)
                self.assertEqual(set(run.data['results'].values()),{'skipped'})
    def test_weekly_dry_run_does_not_create_client(self):
        args=SimpleNamespace(only='sbi_index',retry_run=None,sony_only=False,cloud_only=False,dry_run=True,force=False,run_id=None)
        original=rt.Run
        with tempfile.TemporaryDirectory() as tmp, patch.object(weekly,'parse_args',return_value=args), patch.object(weekly,'load_private_env'), patch.object(weekly,'sb_client',side_effect=AssertionError('network')), patch.object(weekly,'Run',side_effect=lambda *a,**kw:original(*a,**kw,root=Path(tmp))), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(weekly.main(),0)
    def test_weekly_entry_respects_busy_before_collection(self):
        args=SimpleNamespace(only='sbi_index',retry_run=None,sony_only=False,cloud_only=False,dry_run=False,force=False,run_id=None)
        original=rt.Run
        with tempfile.TemporaryDirectory() as tmp, rt.SharedLock(Path(tmp)), patch.object(weekly,'parse_args',return_value=args), patch.object(weekly,'load_private_env'),patch.object(weekly,'sb_client',return_value=Mock()),patch.object(weekly,'Run',side_effect=lambda *a,**kw:original(*a,**kw,root=Path(tmp))), patch.object(weekly,'_collect_main') as collect,contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(weekly.main(),2);collect.assert_not_called()

if __name__=='__main__': unittest.main()
