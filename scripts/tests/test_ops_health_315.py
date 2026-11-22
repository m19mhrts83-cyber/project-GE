from __future__ import annotations
import contextlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_ops_health_315 as ops
import jarvis_ops_health_315_sources as sources


class SourcesTest(unittest.TestCase):
    def test_square_from_watch_status(self):
        now = datetime(2026, 11, 22, 13, 0, tzinfo=timezone.utc)
        def beat(hours):
            return (now - timedelta(hours=hours)).astimezone(timezone(timedelta(hours=9))).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'watch.json'
            self.assertEqual(sources.square_snapshot(p, now)[0], '確認不能')
            cases = [
                ({'state': 'running', 'heartbeat_at': beat(0.1)}, 'OK'),
                ({'state': 'running', 'heartbeat_at': beat(25)}, '確認不能'),
                ({'state': 'running', 'heartbeat_at': beat(-2)}, '確認不能'),
                ({'state': 'running'}, '確認不能'),
                ({'state': 'running', 'heartbeat_at': '2026-11-22T20:00:00'}, '確認不能'),
                ({'state': 'stopped', 'heartbeat_at': beat(1)}, '異常'),
                ({'state': 'running', 'heartbeat_at': beat(1), 'last_write_error': 'x'}, '異常'),
            ]
            for data, expected in cases:
                p.write_text(json.dumps(data))
                before = p.read_bytes()
                self.assertEqual(sources.square_snapshot(p, now)[0], expected, data)
                self.assertEqual(p.read_bytes(), before)
            for bad in ('[]', '{broken'):
                p.write_text(bad)
                self.assertEqual(sources.square_snapshot(p, now)[0], '確認不能')

    def test_gha_completed_main_and_failure(self):
        for rc, payload, level in [(1, '', '確認不能'), (0, '[]', '確認不能'), (0, json.dumps([{'updatedAt': datetime.now(timezone.utc).isoformat(), 'conclusion': 'failure'}]), '異常')]:
            def run(cmd, **kwargs):
                self.assertIn('completed', cmd)
                self.assertIn('main', cmd)
                self.assertIn('ops-health-315.yml', cmd)
                return rc, payload
            self.assertEqual(sources.gha_snapshot(run)[0], level)

    def test_collect_order_and_cloud_no_local(self):
        order = []
        def snapshot(name):
            def call(*args):
                order.append(name)
                return 'OK', ''
            return call
        with patch.object(sources, 'gha_snapshot', side_effect=snapshot('gha')), patch.object(sources, 'square_snapshot', side_effect=snapshot('square')), patch.object(sources, 'chrline_snapshot', side_effect=snapshot('chrline')):
            sources.collect(None, cloud=False)
            self.assertEqual(order, ['gha', 'square', 'chrline'])
            order.clear()
            result = sources.collect(None, cloud=True)
            self.assertEqual(order, ['gha'])
            self.assertEqual(result['Square（オプチャ常駐）'][0], 'スキップ(cloud)')

    def test_collection_separate_from_health(self):
        for levels, result in [(['OK', '異常'], '成功'), (['OK', '確認不能'], '部分成功'), (['確認不能'], '失敗'), (['OK', 'スキップ(cloud)'], '部分成功')]:
            self.assertEqual(sources.collection_result(levels), result)

    def test_chrline_uses_existing_health_no_baseline_and_no_private_output(self):
        # Substitute only the imported health module; never scan real private files.
        from types import SimpleNamespace
        run = unittest.mock.Mock(return_value=({'md_reports': [{'exists': True}]}, 'private'))
        module = SimpleNamespace(load_previous_health=lambda: {}, run_line_health_routine=run,
            build_health_snapshot=lambda inv: {'decode_seen': 25}, evaluate_alerts=lambda cur, prev: ['private'])
        with patch.dict(sys.modules, {'chrline_line_health': module}):
            result = sources.chrline_child()
        run.assert_called_once_with(save_baseline=False)
        self.assertEqual(result[0], '異常')
        self.assertNotIn('private', result[1])


class ChrlineNoSampleTest(unittest.TestCase):
    def _child(self, age):
        from types import SimpleNamespace
        module = SimpleNamespace(load_previous_health=lambda: {}, run_line_health_routine=lambda save_baseline: ({'md_reports': [{'exists': True}]}, ''),
            build_health_snapshot=lambda inv: {'decode_seen': 0}, evaluate_alerts=lambda cur, prev: [])
        with patch.dict(sys.modules, {'chrline_line_health': module}), patch.object(sources, 'sync_age_hours', return_value=age):
            return sources.chrline_child()

    def test_no_sample_but_recent_sync_is_ok_with_reason(self):
        level, text = self._child(3.2)
        self.assertEqual(level, 'OK')
        self.assertIn('新着なし', text)

    def test_no_sample_and_old_or_unknown_sync_is_unconfirmed(self):
        for age in (49, None):
            self.assertEqual(self._child(age)[0], '確認不能')

    def test_sync_age_uses_newest_marker(self):
        import os, time
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(sources.sync_age_hours(Path(d)))
            q = Path(d) / sources.SYNC_MARKERS[0]
            q.write_text('{}')
            os.utime(q, (time.time() - 7200, time.time() - 7200))
            self.assertAlmostEqual(sources.sync_age_hours(Path(d)), 2.0, delta=0.1)


class ChrlineSubprocessTest(unittest.TestCase):
    def snap(self, code, timeout=20):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'py'
            fake.write_text('#!/bin/sh\n' + code + '\n')
            fake.chmod(0o755)
            return sources.chrline_snapshot(fake, timeout)

    def test_ok_result_is_passed_through(self):
        r = self.snap('echo "noise /private/path"; echo \'@@["OK","detail"]\'')
        self.assertEqual(r, ('OK', 'detail'))

    def test_missing_venv(self):
        r = sources.chrline_snapshot(Path('/nonexistent/py'))
        self.assertEqual(r[0], '確認不能')
        self.assertIn('venvなし', r[1])

    def test_child_failure_hides_output(self):
        r = self.snap('echo secret-path >&2; exit 3')
        self.assertEqual(r[0], '確認不能')
        self.assertIn('code=3', r[1])
        self.assertNotIn('secret', r[1])

    def test_timeout(self):
        r = self.snap('sleep 5', timeout=1)
        self.assertEqual(r[0], '確認不能')
        self.assertIn('タイムアウト', r[1])


class PipelineTest(unittest.TestCase):
    def execute(self, argv, source_level='確認不能'):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sys, 'argv', ['315'] + argv), patch.object(ops, 'LOG_DIR', Path(tmp)), patch.object(ops, 'westudy_block', return_value=('OK', '')) as westudy, patch.object(ops, 'openchat_snapshot', return_value=('OK', [])), patch.object(ops, 'gmail_token_snapshot', return_value=('OK', [], [])) as gmail, patch.object(ops, 'collect', return_value={'Square probe': (source_level, 'saved only')}) as collect, patch.object(ops, 'post_ops', return_value=0) as post, patch.object(ops, 'post_slack', return_value=0) as consult, patch.object(ops, '_run') as run, redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(ops.main(), 0)
            return westudy.call_args_list, gmail.call_args_list, post.call_count, consult.call_args_list, run.call_count, stdout.getvalue()

    def test_dry_run_even_post_mark_and_remediation_cannot_mutate(self):
        w, g, posts, consult, runs, out = self.execute(['--post', '--mark-checked', '--remediate-once', '--dry-run'])
        self.assertFalse(w[0].kwargs['mark_checked'])
        self.assertFalse(g[0].kwargs['mark_prompted'])
        self.assertEqual((posts, len(consult), runs), (0, 0, 0))
        self.assertIn('部分成功', out)

    def test_unresolved_sources_consult_without_new_recovery(self):
        _, _, posts, consult, runs, out = self.execute(['--post'])
        self.assertEqual((posts, len(consult), runs), (1, 1, 0))
        self.assertEqual(consult[0].args[0], 'consult')
        self.assertIn('担当メモ:', consult[0].args[1])
        self.assertIn('要フォロー', out)

    def test_normal_posts_without_consult(self):
        _, _, posts, consult, runs, _ = self.execute(['--post'], 'OK')
        self.assertEqual((posts, len(consult), runs), (1, 0, 0))

    def test_weekly_post_has_no_quiet_green(self):
        with patch.dict(ops.os.environ, {'SLACK_WEBHOOK_AI_TEAM_OPS': 'test-only'}), patch.object(ops, '_run', return_value=(0, '')) as run, redirect_stdout(io.StringIO()):
            ops.post_ops('判定: 🟢OK')
        self.assertNotIn('--quiet-green-after', run.call_args.args[0])

    def test_missing_dedicated_webhook_never_falls_back(self):
        with patch.dict(ops.os.environ, {'SLACK_WEBHOOK_AI_TEAM_REPORT': 'test-only'}, clear=True), patch.object(ops, '_run') as run, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ops.post_slack('consult', 'test'), 2)
            run.assert_not_called()

    def test_gmail_invalid_payload_is_unknown(self):
        with patch.object(ops, '_run', return_value=(0, 'invalid')):
            self.assertEqual(ops.gmail_token_snapshot()[0], '確認不能')
        with patch.object(ops, '_run', return_value=(0, '{"issues": [], "nested": {"ok": true}}')):
            self.assertEqual(ops.gmail_token_snapshot()[0], 'OK')

    def test_existing_recovery_once_dry_run_none(self):
        with patch.object(ops, '_run', return_value=(0, 'recovered')) as run:
            ops.try_remediate_once(westudy_line='OK', oc_level='要フォロー', oc_lines=['launchd: running'], dry_run=False)
            self.assertEqual(run.call_count, 2)  # health --push and recover_worker, once each
            run.reset_mock()
            ops.try_remediate_once(westudy_line='OK', oc_level='要フォロー', oc_lines=[], dry_run=True)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
