#!/usr/bin/env python3
"""新着の候補が全部除外で 0 件のとき #ops に黄の注意を出す（ネットワーク不要）。"""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_mail_action_slack_post as ma  # noqa: E402


class _Q:
    def __init__(self, data):
        self._d = data

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        return mock.Mock(data=self._d)


class _SB:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _Q(self._rows)


def _row(i, *, kind, pri, hours_ago=3):
    at = (datetime.now(ma.JST) - timedelta(hours=hours_ago)).isoformat()
    return {
        "id": f"t{i}", "status": "pending", "subject": f"お知らせ{i}", "kind": kind,
        "priority": pri, "lane": "general", "from_email": "a@example.com",
        "draft_text": "", "original_body": "本文", "payload": {}, "received_at": at,
    }


def _load(rows):
    with mock.patch.object(ma, "_sb", return_value=_SB(rows)), \
         mock.patch.object(ma, "load_mute_registry", return_value={"entries": {}}), \
         mock.patch.object(ma, "load_sender_policies", return_value={}):
        return ma.load_pending_from_supabase(limit=5, dry_run=True)


def _run_main(rows, stats, wait=([], {})):
    notify = mock.Mock()
    out = io.StringIO()
    argv = ["x", "--from-triage", "--dry-run"]
    with mock.patch.object(sys, "argv", argv), \
         mock.patch.object(ma, "load_pending_from_supabase", return_value=(rows, stats)), \
         mock.patch.object(ma, "load_reply_wait_from_supabase", return_value=wait), \
         mock.patch.object(ma, "notify_all_excluded_ops", notify), \
         mock.patch.object(ma, "_action_secret", return_value="k"), \
         mock.patch.object(ma, "post_slack", return_value=(0, "C", "1")), \
         mock.patch.object(ma, "mark_gmail_read_after_slack", return_value={"ok": 0}), \
         mock.patch.object(ma, "build_compact_payload", return_value={}), \
         mock.patch.object(ma, "build_digest_payload", return_value={}), \
         mock.patch.object(ma, "should_skip_duplicate_digest", return_value=(False, "")), \
         redirect_stdout(out):
        rc = ma.main()
    return rc, out.getvalue(), notify


class AllExcludedTests(unittest.TestCase):
    def test_all_skim_counts_fresh_excluded(self):
        rows, stats = _load([_row(1, kind="skim", pri="low"), _row(2, kind="skim", pri="low")])
        self.assertEqual(rows, [])
        self.assertEqual(stats["skim_skip"], 2)
        self.assertEqual(stats["fresh_excluded"], 2)
        self.assertTrue(ma.all_excluded_ops_needed(stats, final_rows=0))

    def test_old_skim_is_not_fresh(self):
        rows, stats = _load([_row(1, kind="skim", pri="low", hours_ago=24 * 10)])
        self.assertEqual(stats["fresh_excluded"], 0)
        self.assertFalse(ma.all_excluded_ops_needed(stats, final_rows=0))

    def test_main_all_excluded_warns_ops_and_prints_summary(self):
        stats = {"pending_loaded": 2, "skim_skip": 2, "fresh_excluded": 2, "mute_entries": 44}
        rc, out, notify = _run_main([], stats)
        self.assertEqual(rc, 0)
        notify.assert_called_once()
        last = [ln for ln in out.splitlines() if ln.startswith("# skip_summary:")]
        self.assertEqual(len(last), 1)
        self.assertIn("skim_skip=2", last[0])
        self.assertIn("posted=0", last[0])

    def test_main_nothing_pending_no_warning(self):
        rc, out, notify = _run_main([], {"pending_loaded": 0, "fresh_excluded": 0})
        self.assertEqual(rc, 0)
        notify.assert_not_called()

    def test_main_with_posted_card_no_warning(self):
        row = {"id": "t9", "subject": "Re: 見積", "payload": {}, "_score": 5}
        stats = {"pending_loaded": 3, "skim_skip": 2, "fresh_excluded": 2}
        rc, out, notify = _run_main([row], stats)
        self.assertEqual(rc, 0)
        notify.assert_not_called()
        self.assertIn("# skip_summary: posted=1", out)

    def test_ops_text_has_no_private_details(self):
        t = ma.all_excluded_ops_text({"fresh_excluded": 3, "skim_skip": 3})
        self.assertIn("🟡【ops】", t)
        self.assertIn("3件", t)


if __name__ == "__main__":
    unittest.main()
