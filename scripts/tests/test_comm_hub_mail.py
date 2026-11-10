#!/usr/bin/env python3
"""comm hub メール取込（inquiry / 自分の送信）のテスト（ネットワーク不要）。"""
from __future__ import annotations

import base64
import sys
import argparse
import unittest
from unittest import mock
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


class IdempotentSoftFailTest(unittest.TestCase):
    """2回走っても重複しない・失敗しても止めない（PR #333 の確認項目）。"""

    def test_same_input_same_external_id(self):
        a = mail.item_from_triage(_triage())
        b = mail.item_from_triage(_triage())
        self.assertEqual(a["external_id"], b["external_id"])
        s1 = mail.item_from_sent(_sent("x@example.jp"), account="admin", partner_filter=lambda _: False)
        s2 = mail.item_from_sent(_sent("x@example.jp"), account="admin", partner_filter=lambda _: False)
        self.assertEqual((s1["channel"], s1["account"], s1["external_id"]), (s2["channel"], s2["account"], s2["external_id"]))

    def test_insert_uses_ignore_duplicates(self):
        import jarvis_comm_hub as hub

        sb = mock.MagicMock()
        with mock.patch.object(hub, "ensure_parties"), mock.patch.object(hub, "lookup_ids", return_value={}):
            hub.insert_items(sb, [mail.item_from_triage(_triage())])
            hub.insert_items(sb, [mail.item_from_triage(_triage())])
        calls = sb.table.return_value.upsert.call_args_list
        self.assertEqual(len(calls), 2)
        for c in calls:
            self.assertEqual(c.kwargs["on_conflict"], "channel,account,external_id")
            self.assertTrue(c.kwargs["ignore_duplicates"])

    def test_triage_link_does_not_overwrite(self):
        import jarvis_comm_hub as hub

        sb = mock.MagicMock()
        with mock.patch.object(hub, "client", return_value=sb), \
             mock.patch.object(mail, "fetch_general_mail", return_value=[_triage()]), \
             mock.patch.object(hub, "insert_items", return_value={"gmail:m1": "item-1"}), \
             mock.patch.object(hub, "link_items") as link:
            rc = mail.cmd_ingest_triage(argparse.Namespace(days=14, apply=True, dry_run=False))
        self.assertEqual(rc, 0)
        sb.table.return_value.update.return_value.eq.return_value.is_.assert_called_with("comm_item_id", "null")
        link.assert_called_once()

    def test_sent_account_failure_is_soft(self):
        with mock.patch.object(mail, "gmail_service", side_effect=RuntimeError("token missing")), \
             mock.patch("jarvis_comm_hub.resolve_contact_yaml", return_value=Path("/nonexistent.yaml")):
            rc = mail.cmd_ingest_sent(argparse.Namespace(account=["admin", "estate"], days=3, max=10, apply=False, dry_run=True))
        self.assertEqual(rc, 0)

    def test_runner_soft_fails_each_step(self):
        runner = (REPO / "launchd" / "comm_hub_mail_runner.sh").read_text(encoding="utf-8")
        self.assertIn('ingest-mail-triage --days 14 --apply || echo "# comm hub soft-fail', runner)
        self.assertIn('ingest-mail-sent --account admin --account estate --days 3 --apply || echo "# comm hub soft-fail', runner)


if __name__ == "__main__":
    unittest.main()
