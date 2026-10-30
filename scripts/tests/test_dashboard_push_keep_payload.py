#!/usr/bin/env python3
"""dashboard_push が投稿済み印（slack_ma_*）を消さないことの単体テスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_dashboard_push as dp  # noqa: E402


class KeepRemotePayloadMetaTests(unittest.TestCase):
    def test_keeps_slack_ma_and_listed_keys(self):
        remote = {
            "slack_ma_posted_at": "2026-10-30T05:02:42+0900",
            "slack_ma_digest": {"score": 3},
            "gmail_read_at": "2026-10-30T05:03:00+0900",
            "sent_at": "x",
            "reason": "old",
            "slack_ma_ts": None,
        }
        out = dp.keep_remote_payload_meta({"reason": "new"}, remote, ("sent_at",))
        self.assertEqual(out["slack_ma_posted_at"], "2026-10-30T05:02:42+0900")
        self.assertEqual(out["slack_ma_digest"], {"score": 3})
        self.assertEqual(out["gmail_read_at"], "2026-10-30T05:03:00+0900")
        self.assertEqual(out["sent_at"], "x")
        self.assertEqual(out["reason"], "new")
        self.assertNotIn("slack_ma_ts", out)


if __name__ == "__main__":
    unittest.main()
