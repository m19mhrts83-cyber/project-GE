import contextlib
from datetime import datetime
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_asset_618_observe as monitor
import jarvis_asset_618_report as report

NOW = datetime(2026, 11, 14, 12, tzinfo=report.JST)


def database():
    return {'portfolio': {'accounts_ok': True, 'snapshots_ok': True,
        'accounts': [{'id': x} for x in ('axa_life', 'sony_life', 'sony_life_sovani_kids', 'prudential_life')],
        'snapshots': [
            {'account_id': 'axa_life', 'as_of': '2026-11-10', 'source': 'weekly_web'},
            {'account_id': 'sony_life', 'as_of': '2026-10-26', 'source': 'weekly_web'},
            {'account_id': 'prudential_life', 'as_of': '2026-11-10', 'source': 'weekly_manual'}]},
        'liquidity': {'accounts_ok': True, 'snapshots_ok': True, 'accounts': [], 'snapshots': [], 'excluded_non_balance': ['amex']}}


class ObserveTests(unittest.TestCase):
    def test_inventory_separates_saved_old_missing_and_manual(self):
        r = monitor.inventory(database(), {'ok': True, 'rows': []}, now=NOW)
        self.assertEqual(r['database_counts'], {'current_week': 2, 'older': 1, 'missing': 1})
        self.assertEqual(r['manual_reference_count'], 1)
        self.assertEqual(r['excluded_cards'], 1)
        self.assertIn('ソニー子ども契約', r['slack_text'])
        self.assertEqual(r['current_write'], 'not_verified')
        self.assertEqual(r['kurashift_display'], 'not_verified')

    def test_no_images_is_unregistered_not_capture_failure(self):
        r = monitor.inventory(database(), {'ok': True, 'rows': []}, now=NOW)
        self.assertEqual(r['image_counts'], {'not_registered': 4})
        self.assertIn('未登録は撮影失敗を意味しません', r['slack_text'])

    def test_failed_update_keeps_previous_good_distinct(self):
        r = monitor.inventory(database(), {'ok': True, 'rows': [{
            'account_scope': 'portfolio', 'account_id': 'axa_life', 'active_slot': 'a',
            'captured_at': '2026-11-10T10:00:00Z', 'source_as_of': '2026-11-10',
            'last_attempt_status': 'failed'}]}, now=NOW)
        self.assertEqual(r['image_counts']['previous_good_held'], 1)

    def test_unavailable_not_empty_success(self):
        r = monitor.inventory({}, {'ok': False, 'rows': []}, now=NOW)
        self.assertFalse(r['scope_verified'])
        self.assertGreater(r['database_read_failures'], 0)
        self.assertIn('読取障害', r['slack_text'])
        self.assertIn('読取不可', r['slack_text'])

    def test_approval_and_finite_expiry_required(self):
        for approved, until in [(None, None), ('false', '2026-12-12'), ('true', ''),
                                ('true', '2026-11-13'), ('true', '2027-01-01')]:
            self.assertFalse(monitor.posting_allowed(NOW, approved, until))
        self.assertTrue(monitor.posting_allowed(NOW, 'true', '2026-12-12'))

    def test_normal_days_still_generate_message(self):
        d = database()
        d['portfolio']['accounts'] = [{'id': 'axa_life'}]
        r = monitor.inventory(d, {'ok': True, 'rows': []}, now=NOW)
        self.assertIn('確認処理は正常', r['slack_text'])
        self.assertIn('数値DB', r['slack_text'])

    def test_unknown_names_and_raw_exceptions_never_leave(self):
        d = database()
        d['portfolio']['accounts'] = [{'id': 'SECRET_ACCOUNT_NAME'}]
        r = monitor.inventory(d, {'ok': True, 'rows': []}, now=NOW)
        self.assertNotIn('SECRET_ACCOUNT_NAME', json.dumps(r))
        client = MagicMock()
        client.table.side_effect = RuntimeError('SECRET_TOKEN')
        self.assertEqual(monitor.read_images(client), {'ok': False, 'rows': []})

    def test_default_and_unapproved_post_never_send(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(monitor, 'db_client'), \
             patch.object(monitor, 'read_database', return_value=database()), \
             patch.object(monitor, 'read_images', return_value={'ok': True, 'rows': []}), \
             patch.object(monitor.urllib.request, 'urlopen') as send, \
             patch.dict(os.environ, {'ASSET618_REPORT_APPROVED': ''}), contextlib.redirect_stdout(io.StringIO()):
            monitor.main(['--out', tmp])
            monitor.main(['--out', tmp, '--post'])
            send.assert_not_called()
            self.assertTrue((Path(tmp) / 'slack_draft.txt').exists())

    def test_cards_excluded_in_database_reader(self):
        client = MagicMock()
        accounts = client.table.return_value.select.return_value.eq.return_value.order.return_value
        accounts.range.return_value.execute.return_value.data = [{'id': 'amex', 'kind': 'card'}, {'id': 'wallet', 'kind': 'cash'}]
        snapshots = client.table.return_value.select.return_value.in_.return_value.order.return_value.order.return_value
        snapshots.range.return_value.execute.return_value.data = []
        r = report.read_database(client)
        self.assertEqual(r['liquidity']['accounts'], [{'id': 'wallet', 'kind': 'cash'}])
        self.assertEqual(r['liquidity']['excluded_non_balance'], ['amex'])

    def test_child_contract_is_in_collection_target_set(self):
        import jarvis_portfolio_weekly as weekly
        self.assertIn('sony_life_sovani_kids', weekly.ALL_TARGETS)

    def test_missing_child_value_is_held_not_zero_filled(self):
        import jarvis_portfolio_weekly as weekly
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        with patch.object(weekly, 'fetch_sony_by_account', return_value={'status': 'ok', 'accounts': {}, 'loans': {}}), \
             patch.object(weekly, 'estimate_sony_costs_from_zaim', return_value={'sony_life_sovani_kids': {'cost_jpy': 123}}), \
             patch.object(weekly, 'target_allowed', side_effect=lambda x: x == 'sony_life_sovani_kids'), \
             patch.object(weekly, 'upsert_snapshot') as write, contextlib.redirect_stdout(io.StringIO()):
            sources = {}
            weekly.ingest_sony(db, sources, dry_run=False)
            self.assertEqual(sources['sony_life_sovani_kids']['status'], 'skipped')
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
