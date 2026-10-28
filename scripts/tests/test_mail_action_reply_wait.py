#!/usr/bin/env python3
"""後回し（Todoist）返信の再掲候補テスト（ネットワーク不要）。"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_mail_action_slack_post as ma  # noqa: E402


class _Q:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def table(self, _n):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def update(self, data):
        self.updates.append(data)
        return self

    def execute(self):
        return type("R", (), {"data": self.rows})()


def _row(tid, task_id, **pl):
    return {
        "id": tid,
        "status": "todoist",
        "subject": f"件名{tid}",
        "partner": "LEAF",
        "from_email": "x@leaf-eco.com",
        "original_body": "松野 様\nお世話になります。LEAFの神野です。",
        "payload": {"todoist_task_id": task_id, **pl},
    }


class ReplyWaitTests(unittest.TestCase):
    def test_due_open_tasks_resurface_once_per_day(self):
        today = datetime.now(ma.JST).strftime("%Y-%m-%d")
        later = (datetime.now(ma.JST) + timedelta(days=3)).strftime("%Y-%m-%d")
        rows = [
            _row("due", "t1"),
            _row("later", "t2"),
            _row("closed", "t3"),
            _row("posted_today", "t4", slack_ma_wait_posted_on=today),
            _row("already_closed", "t5", todoist_closed_at="x"),
        ]
        states = {
            "t1": {"closed": False, "due": today},
            "t2": {"closed": False, "due": later},
            "t3": {"closed": True, "due": None},
            "t4": {"closed": False, "due": today},
        }
        q = _Q(rows)
        with mock.patch.dict(os.environ, {"TODOIST_API_TOKEN": "x"}), mock.patch.object(
            ma, "_sb", return_value=q
        ), mock.patch.object(ma, "todoist_task_state", side_effect=lambda t: states.get(t)):
            out, stats = ma.load_reply_wait_from_supabase(limit=3)
        self.assertEqual([r["id"] for r in out], ["due"])
        self.assertTrue(out[0]["_reply_wait"])
        self.assertIn("後回し", out[0]["_extract_summary"])
        self.assertEqual(stats["wait_closed"], 1)
        self.assertEqual(stats["wait_later"], 1)
        self.assertTrue(any("todoist_closed_at" in u.get("payload", {}) for u in q.updates))
        self.assertIn("⏰後回し", ma.digest_index_line(out[0], index=1))

    def test_no_token_no_wait(self):
        with mock.patch.dict(os.environ, {"TODOIST_API_TOKEN": ""}):
            out, _ = ma.load_reply_wait_from_supabase(limit=3)
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
