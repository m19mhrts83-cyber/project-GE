#!/usr/bin/env python3
"""地場業者返信の誤送信再発防止テスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_kurashift_vendor_reply_triage as triage  # noqa: E402
import jarvis_vendor_reply_slack_post as slack_post  # noqa: E402


class VendorReplySendSafetyTests(unittest.TestCase):
    def test_google_noreply_is_never_a_vendor_reply_candidate(self):
        self.assertTrue(
            triage.is_unsafe_vendor_reply_sender("noreply-accounts@google.com")
        )
        self.assertTrue(triage.is_unsafe_vendor_reply_sender("no-reply@google.com"))
        self.assertTrue(triage.is_unsafe_vendor_reply_sender("noreplyto@crm.athome.jp"))
        self.assertFalse(triage.is_unsafe_vendor_reply_sender("info@taishi-estate.jp"))

    def test_interactive_slack_card_does_not_expose_signed_action_urls(self):
        row = {
            "id": "re-vendor-12345678",
            "partner": "テスト不動産",
            "subject": "お問い合わせありがとうございます",
            "original_body": "受信本文",
            "draft_text": "返信草案",
            "payload": {"re_vendor_reply": True, "vendor_id": "test-1"},
        }
        payload = slack_post.build_payload(row, url_mode=False)
        serialized = str(payload)
        self.assertNotIn("/api/g/vr/", serialized)
        self.assertIn("vendor_reply_send", serialized)

    def test_url_fallback_opens_confirmation_route(self):
        row = {
            "id": "re-vendor-12345678",
            "partner": "テスト不動産",
            "subject": "お問い合わせありがとうございます",
            "original_body": "受信本文",
            "draft_text": "返信草案",
            "payload": {"re_vendor_reply": True, "vendor_id": "test-1"},
        }
        payload = slack_post.build_payload(row, url_mode=True)
        self.assertIn("/api/g/vr/send/", str(payload))
        self.assertIn("送信確認", str(payload))


if __name__ == "__main__":
    unittest.main()
