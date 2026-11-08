#!/usr/bin/env python3
"""ループウェアで「要対応だった」とされた見落としの扱い（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_mail_action_slack_post as ma  # noqa: E402


class LoopwareMissTests(unittest.TestCase):
    def test_due_until_reposted(self):
        self.assertTrue(ma.is_loopware_miss_due({"loopware_miss": True}))
        self.assertFalse(ma.is_loopware_miss_due({"loopware_miss": True, "slack_ma_miss_posted_at": "x"}))
        self.assertFalse(ma.is_loopware_miss_due({}))
        self.assertFalse(ma.is_loopware_miss_due(None))

    def test_miss_ranks_first(self):
        normal = {"id": "a1", "subject": "Re: 見積の件", "priority": "high", "payload": {}}
        miss = {"id": "b2", "subject": "カード利用のお知らせ", "payload": {"loopware_miss": True}}
        ranked = ma.rank_candidates([normal, miss], limit=2)
        self.assertEqual(ranked[0]["id"], "b2")
        self.assertIn("loopware:miss", ranked[0]["_score_reasons"])

    def test_stamp_marks_repost_once(self):
        out = ma._stamp_posted_payload(
            {"loopware_miss": True}, score=1, summary="", slack_channel=None,
            slack_ts=None, digest_channel=None, digest_ts=None,
        )
        self.assertTrue(out.get("slack_ma_miss_posted_at"))
        self.assertFalse(ma.is_loopware_miss_due(out))


if __name__ == "__main__":
    unittest.main()
