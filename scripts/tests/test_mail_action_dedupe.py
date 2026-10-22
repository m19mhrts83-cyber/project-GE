#!/usr/bin/env python3
"""116 / 211 Slack 重複投稿防止の単体テスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_mail_action_slack_post as ma  # noqa: E402
import jarvis_reply_draft_211 as r211  # noqa: E402


class MailActionDedupeTests(unittest.TestCase):
    def test_gmail_id_collapses_gha_pair(self):
        rows = [
            {
                "id": "gha-abc",
                "gmail_message_id": "mid-1",
                "subject": "Hello",
                "partner": "X",
                "_score": 10,
            },
            {
                "id": "abc",
                "gmail_message_id": "mid-1",
                "subject": "Hello",
                "partner": "X",
                "_score": 10,
            },
        ]
        out, dropped = ma.dedupe_candidates(rows)
        self.assertEqual(dropped, 1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "abc")

    def test_higher_score_wins(self):
        rows = [
            {
                "id": "a",
                "gmail_message_id": "mid-2",
                "_score": 5,
            },
            {
                "id": "b",
                "gmail_message_id": "mid-2",
                "_score": 50,
            },
        ]
        out, dropped = ma.dedupe_candidates(rows)
        self.assertEqual(dropped, 1)
        self.assertEqual(out[0]["id"], "b")

    def test_empty_subject_same_partner_date(self):
        rows = [
            {
                "id": "1",
                "partner": "Tcell",
                "subject": "(件名なし)",
                "received_at": "2026/10/21",
                "from_email": "",
                "original_body": "",
                "_score": 20,
            },
            {
                "id": "2",
                "partner": "Tcell",
                "subject": "(件名なし)",
                "received_at": "2026/10/21",
                "from_email": "",
                "original_body": "",
                "_score": 20,
            },
        ]
        out, dropped = ma.dedupe_candidates(rows)
        self.assertEqual(dropped, 1)
        self.assertEqual(len(out), 1)

    def test_rank_candidates_applies_dedupe_before_limit(self):
        rows = []
        for i in range(3):
            rows.append(
                {
                    "id": f"gha-{i}",
                    "gmail_message_id": "same-mid",
                    "subject": "dup",
                    "partner": "P",
                    "priority": "high",
                    "kind": "mail",
                    "lane": "partner",
                    "original_body": "ご確認ください",
                    "received_at": "2026-10-21T10:00:00+09:00",
                }
            )
        ranked = ma.rank_candidates(rows, limit=5)
        self.assertEqual(len(ranked), 1)


class Reply211DedupeTests(unittest.TestCase):
    def test_b_waiting_dedupes_same_folder_empty_subject(self):
        items = [
            {
                "folder": "P103_Tcell",
                "subject": "(件名なし)",
                "received_at": "2026/10/21",
            },
            {
                "folder": "P103_Tcell",
                "subject": "(件名なし)",
                "received_at": "2026/10/21",
            },
            {
                "folder": "P101_ホームプランナー",
                "subject": "(件名なし)",
                "received_at": "2026/10/20",
            },
        ]
        out = r211._dedupe_b_waiting(items)
        self.assertEqual(len(out), 2)
        folders = {x["folder"] for x in out}
        self.assertEqual(folders, {"P103_Tcell", "P101_ホームプランナー"})


if __name__ == "__main__":
    unittest.main()
