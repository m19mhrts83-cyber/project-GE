#!/usr/bin/env python3
"""comm hub メール取込（inquiry / 自分の送信）のテスト（ネットワーク不要）。"""
from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_comm_hub_mail as mail  # noqa: E402


def _triage(**kw):
    row = {
        "id": "abc123",
        "status": "pending",
        "subject": "賃貸のご相談",
        "partner": "山田不動産",
        "from_email": "yamada@example.jp",
        "priority": "high",
        "summary": "空室の相談",
        "original_body": "本文です",
        "received_at": "2026/11/08 09:08",
        "account": "estate",
        "gmail_thread_id": "t1",
        "gmail_message_id": "m1",
        "channel": "業者返信（estate）",
        "payload": {"source": "vendor_reply_triage"},
    }
    row.update(kw)
    return row


def _sent(to: str, subject: str = "ご相談", body: str = "よろしくお願いします") -> dict:
    data = base64.urlsafe_b64encode(body.encode()).decode()
    return {
        "id": "s1",
        "threadId": "th1",
        "internalDate": "1762740000000",
        "snippet": body,
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "To", "value": to}, {"name": "Subject", "value": subject}],
            "body": {"data": data},
        },
    }


class TriageTest(unittest.TestCase):
    def test_row(self):
        it = mail.item_from_triage(_triage())
        self.assertEqual(it["category"], "inquiry")
        self.assertEqual(it["external_id"], "gmail:m1")
        self.assertEqual(it["account"], "estate")
        self.assertEqual(it["work_status"], "needs_reply")
        self.assertEqual(it["source_ref"]["triage_id"], "abc123")
        self.assertTrue(it["occurred_at"].startswith("2026-11-08T09:08"))

    def test_status_map(self):
        self.assertEqual(mail.item_from_triage(_triage(status="skipped"))["work_status"], "no_action")
        self.assertEqual(mail.item_from_triage(_triage(status="sent"))["work_status"], "done")

    def test_no_message_id(self):
        self.assertEqual(mail.item_from_triage(_triage(gmail_message_id=None))["external_id"], "triage:abc123")

    def test_secret_excluded(self):
        self.assertIsNone(mail.item_from_triage(_triage(subject="【確認コード】123456")))


class SentTest(unittest.TestCase):
    def test_external_recipient(self):
        it = mail.item_from_sent(_sent("田中様 <tanaka@example.jp>"), account="admin", partner_filter=lambda a: False)
        self.assertEqual(it["category"], "self")
        self.assertEqual(it["direction"], "outbound")
        self.assertEqual(it["source_ref"]["gmail_message_id"], "s1")

    def test_partner_skipped(self):
        self.assertIsNone(mail.item_from_sent(_sent("p@partner.jp"), account="admin", partner_filter=lambda a: True))

    def test_self_addressed_skipped(self):
        it = mail.item_from_sent(
            _sent("admin@livingsupport-matsu.co.jp", subject="[Grok調査] 常滑市"),
            account="admin",
            partner_filter=lambda a: False,
        )
        self.assertIsNone(it)

    def test_secret_skipped(self):
        it = mail.item_from_sent(_sent("x@example.jp", subject="パスワード再設定"), account="admin", partner_filter=lambda a: False)
        self.assertIsNone(it)


if __name__ == "__main__":
    unittest.main()
