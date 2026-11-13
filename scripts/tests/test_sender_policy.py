#!/usr/bin/env python3
"""送り手ごとの「次回から」（Slack 投稿側）のテスト。ネットワーク不要。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_mail_action_slack_post as ma  # noqa: E402


class SenderPolicyTests(unittest.TestCase):
    def test_policy_lookup_by_address(self):
        pol = {"from:a@x.jp": "hide", "from:b@y.jp": "always"}
        self.assertEqual(ma.sender_policy(pol, "山本 <A@X.jp>"), "hide")
        self.assertEqual(ma.sender_policy(pol, "b@y.jp"), "always")
        self.assertIsNone(ma.sender_policy(pol, "c@z.jp"))
        self.assertIsNone(ma.sender_policy(pol, "名前だけ"))

    def test_auto_close_marks_payload_and_only_pending(self):
        calls = {}

        class Q:
            def update(self, v):
                calls["update"] = v
                return self

            def eq(self, k, v):
                calls.setdefault("eq", []).append((k, v))
                return self

            def execute(self):
                return None

        class SB:
            def table(self, name):
                calls["table"] = name
                return Q()

        ok = ma.auto_close_by_policy(SB(), {"id": "gha-1", "payload": {"x": 1}})
        self.assertTrue(ok)
        self.assertEqual(calls["update"]["status"], "done")
        self.assertEqual(calls["update"]["payload"]["x"], 1)
        self.assertEqual(calls["update"]["payload"]["loopware_auto_policy"]["source"], "auto_policy")
        self.assertIn(("status", "pending"), calls["eq"])


if __name__ == "__main__":
    unittest.main()
