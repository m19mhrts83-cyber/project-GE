from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_asset_618_report as report

NOW = datetime(2026, 11, 14, 17, tzinfo=report.JST)


def state(sources=None, **extra):
    return {'iso_week': '2026-W46', 'finished_at': '2026-11-13T16:00:00+09:00',
            'last_full_ok': True, 'sources': sources or {'axa_life': {'status': 'ok'}}, **extra}


def database(accounts=('axa_life',), rows=None, liquidity=()):
    return {'portfolio': {'accounts_ok': True, 'snapshots_ok': True,
                         'accounts': [{'id': x} for x in accounts],
                         'snapshots': rows if rows is not None else [
                             {'account_id': 'axa_life', 'as_of': '2026-11-13', 'source': 'weekly_web'}]},
            'liquidity': {'accounts_ok': True, 'snapshots_ok': True,
                          'accounts': [{'id': x} for x in liquidity], 'snapshots': []}}


class ResultClassification(unittest.TestCase):
    def test_legacy_full_ok_does_not_hide_skipped_or_omitted_accounts(self):
        s = state({'axa_life': {'status': 'ok'}, 'sony_life': {'status': 'skipped'}})
        r = report.build_report(s, database(('axa_life', 'sony_life', 'bloomo')), now=NOW)
        self.assertEqual(r['overall'], 'partial_or_unverified')
        self.assertEqual(r['collection_counts'], {'reported_ok': 1, 'unverified': 1, 'skipped': 1})

    def test_existing_db_and_ok_are_not_proof_of_this_write_or_display(self):
        r = report.build_report(state(), database(), now=NOW)
        self.assertEqual(r['overall'], 'metadata_consistent')
        self.assertEqual(r['current_write'], 'not_verified')
        self.assertEqual(r['kurashift_display'], 'not_verified')
        self.assertIn('今回の書込は未検証', r['drafts']['report'])

    def test_no_requested_image_does_not_fail_a_numeric_result(self):
        r = report.build_report(state(), database(), now=NOW)
        self.assertEqual(r['image_update'], 'not_requested_not_checked')
        self.assertNotIn('consult', r['drafts'])

    def test_cloud_only_run_does_not_claim_full_login_collection(self):
        r = report.build_report(state(cloud_only=True), database(), now=NOW)
        self.assertEqual(r['collection_counts'], {'unverified': 1})
        self.assertEqual(r['overall'], 'partial_or_unverified')

    def test_old_or_missing_db_date_is_not_current(self):
        for day, expected in [('2026-11-01', 'older'), ('not-a-date', 'missing'),
                              ('2026-12-01', 'invalid_date')]:
            with self.subTest(day=day):
                db = database(rows=[{'account_id': 'axa_life', 'as_of': day}])
                r = report.build_report(state(), db, now=NOW)
                self.assertEqual(r['items'][0]['database'], expected)
                self.assertEqual(r['overall'], 'partial_or_unverified')

    def test_old_run_is_not_current_even_with_recent_database(self):
        r = report.build_report(state(finished_at='2026-11-01T12:00:00+09:00'), database(), now=NOW)
        self.assertEqual(r['collection_counts'], {'unverified': 1})
        self.assertIn('以前または日時不明', r['drafts']['report'])

    def test_naive_future_or_conflicting_week_timestamp_is_not_success(self):
        for fields in [{'finished_at': '2026-11-13T12:00:00'},
                       {'finished_at': '2026-11-15T12:00:00+09:00'}, {'iso_week': '2026-W45'}]:
            with self.subTest(fields=fields):
                r = report.build_report(state(**fields), database(), now=NOW)
                self.assertEqual(r['collection_counts'], {'unverified': 1})

    def test_preserved_ok_and_manual_values_are_reference(self):
        for rec, source in [({'status': 'ok', 'note': 'preserved (later error)'}, 'weekly_web'),
                            ({'status': 'ok', 'note': 'reused same-week ok'}, 'weekly_web'),
                            ({'status': 'ok'}, 'weekly_manual')]:
            with self.subTest(rec=rec, source=source):
                db = database(rows=[{'account_id': 'axa_life', 'as_of': '2026-11-13', 'source': source}])
                r = report.build_report(state({'axa_life': rec}), db, now=NOW)
                self.assertEqual(r['collection_counts'], {'reference': 1})

    def test_current_failed_attempt_is_not_hidden_by_old_db_value(self):
        r = report.build_report(state({'axa_life': {'status': 'error'}}), database(), now=NOW)
        self.assertEqual(r['collection_counts'], {'failed': 1})
        self.assertEqual(r['database_counts'], {'current_week': 1})
        self.assertIn('ops', r['drafts'])

    def test_operation_success_is_not_bank_account_success(self):
        r = report.build_report(state({'liquidity_weekly': {'status': 'ok'},
                                      'akatsuki_zaim': {'status': 'ok'}}),
                                database(accounts=(), rows=[], liquidity=('bank-secret',)), now=NOW)
        self.assertEqual(r['target_count'], 1)
        self.assertEqual(r['collection_counts'], {'unverified': 1})
        self.assertEqual(r['operations']['liquidity_weekly'], 'ok')

    def test_no_db_or_failed_scope_is_never_complete(self):
        for db in (None, {}, {'portfolio': {'accounts_ok': True, 'snapshots_ok': False,
                                          'accounts': [{'id': 'axa_life'}]}}):
            with self.subTest(db=db):
                r = report.build_report(state(), db, now=NOW)
                self.assertFalse(r['scope_verified'])
                self.assertEqual(r['overall'], 'partial_or_unverified')
                if db is not None:
                    self.assertIn('ops', r['drafts'])

    def test_empty_or_malformed_sources_are_not_a_successful_run(self):
        for sources in ({}, [], None, 'secret'):
            r = report.build_report({'sources': sources}, now=NOW)
            self.assertFalse(r['state_valid'])
            self.assertIn('ops', r['drafts'])

    def test_untrusted_free_text_numbers_names_urls_and_ids_do_not_escape(self):
        secret = 'token=PRIVATE_TOKEN口座123456789残高987654321https://private.example/x'
        s = state({'axa_life': {'status': 'error', 'reason': secret, 'value_jpy': 987654321},
                   secret: {'status': secret}})
        db = database(accounts=('axa_life', secret), rows=[
            {'account_id': secret, 'as_of': '2026-11-13', 'source': secret, 'value_jpy': 987654321}])
        serialized = json.dumps(report.build_report(s, db, now=NOW), ensure_ascii=False)
        for sensitive in ['PRIVATE_TOKEN', '123456789', '987654321', 'private.example', 'value_jpy']:
            self.assertNotIn(sensitive, serialized)


class SelectOnlyDB:
    def __init__(self, tables, fail=None):
        self.tables, self.fail, self.selects = tables, fail, []

    def table(self, name):
        client = self

        class Query:
            def select(self, columns):
                client.selects.append((name, columns))
                return self
            def eq(self, *args): return self
            def order(self, *args, **kwargs): return self
            def in_(self, *args): return self
            def range(self, low, high):
                self.low, self.high = low, high
                return self
            def execute(self):
                if name == client.fail:
                    raise RuntimeError('PRIVATE_TOKEN https://secret')
                return type('Response', (), {'data': client.tables.get(name, [])[self.low:self.high + 1]})()
        return Query()


class ReadOnlyAndCLI(unittest.TestCase):
    def test_reader_paginates_and_does_not_select_balances_or_free_text(self):
        tables = {'portfolio_accounts': [{'id': 'asset' + str(i)} for i in range(501)],
                  'portfolio_snapshots': [{'account_id': 'asset0', 'as_of': '2026-11-13', 'source': 'zaim'}]}
        client = SelectOnlyDB(tables)
        db = report.read_database(client)
        self.assertEqual(len(db['portfolio']['accounts']), 501)
        self.assertTrue(db['portfolio']['snapshots_ok'])
        for _, columns in client.selects:
            self.assertNotIn('jpy', columns)
            self.assertNotIn('note', columns)
            self.assertNotIn('name', columns)

    def test_read_error_is_explicit_without_leaking_exception(self):
        client = SelectOnlyDB({'portfolio_accounts': [{'id': 'axa_life'}]}, fail='portfolio_snapshots')
        r = report.build_report(state(), report.read_database(client), now=NOW)
        self.assertEqual(r['database_read_failures'], 1)
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(r))

    def test_cli_writes_only_sanitized_drafts_and_no_send_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'state.json'
            path.write_text(json.dumps(state({'axa_life': {'status': 'error', 'reason': 'PRIVATE_TOKEN'}})))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = report.main(['--state', str(path), '--out', str(root / 'out')])
            self.assertEqual(status, 0)
            self.assertNotIn('PRIVATE_TOKEN', stdout.getvalue())
            self.assertEqual({p.name for p in (root / 'out').iterdir()}, {'report.json', 'slack_drafts.txt'})
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                report.main(['--send'])

    def test_cli_missing_or_non_object_state_is_not_silent_success(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.json'
            for content in ('not-json', '[]', '{}'):
                path.write_text(content)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(report.main(['--state', str(path)]), 2)


if __name__ == '__main__':
    unittest.main()
