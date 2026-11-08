#!/usr/bin/env python3
"""ループウェア見張りファイル（build_status）のテスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_loopware_status as st  # noqa: E402

# 2026-11-11（水）12:00 JST
WED = datetime(2026, 11, 11, 3, 0, tzinfo=timezone.utc)
# 2026-11-14（土）16:00 JST
SAT_AFTER = datetime(2026, 11, 14, 7, 0, tzinfo=timezone.utc)


def at(now, days):
    return (now - timedelta(days=days)).isoformat()


class BuildStatusTests(unittest.TestCase):
    def test_counts_and_stopped_source(self):
        rows = [
            {"decided_at": at(WED, 9), "source": "slack", "action": "skipped", "surface": "triage", "payload": {}},
            {"decided_at": at(WED, 10), "source": "slack", "action": "skipped", "surface": "triage", "payload": {}},
            {"decided_at": at(WED, 11), "source": "slack_ma", "action": "sent", "surface": "triage", "payload": {}},
            {"decided_at": at(WED, 1), "source": "loopware", "action": "hesitated", "surface": "triage", "payload": {}},
            {"decided_at": at(WED, 2), "source": "trade_desk", "action": "adopt", "surface": "kurashift_deal", "payload": {}},
        ]
        s = st.build_status(rows, now=WED, candidates_meta={"at": "2026-11-07T09:02:00+09:00"}, pending_desk=4)
        self.assertEqual(s["sources"]["slack"]["week"], 0)
        self.assertEqual(s["sources"]["slack"]["prev_week"], 3)
        self.assertEqual(s["sources"]["kurashift"]["week"], 1)
        self.assertEqual(s["desk_pending"], 4)
        self.assertEqual(s["week"]["hesitate"], 1)
        self.assertTrue(any("slack" in p for p in s["problems"]))
        # 直近の土曜（11/07）の分は置かれているので遅れは言わない
        self.assertFalse(any("今週の学び" in p for p in s["problems"]))

    def test_weekly_missing_after_saturday_15(self):
        s = st.build_status([], now=SAT_AFTER, candidates_meta={"at": "2026-11-07T09:01:00+09:00"}, pending_desk=0)
        self.assertTrue(any("今週の学び" in p for p in s["problems"]))
        s = st.build_status([], now=SAT_AFTER, candidates_meta={"at": "2026-11-14T09:01:00+09:00", "candidates": [1, 2]}, pending_desk=0)
        self.assertFalse(s["problems"])
        self.assertEqual(s["weekly"]["candidates"], 2)

    def test_naive_or_bad_published_at_does_not_crash(self):
        for v in ("2026-11-14T09:01:00", "not-a-date"):
            s = st.build_status([], now=SAT_AFTER, candidates_meta={"at": v}, pending_desk=0)
            self.assertIsInstance(s["problems"], list)

    def test_rules_pending_apply(self):
        rows = [{"decided_at": at(WED, 1), "source": "loopware", "action": "rule_accept", "surface": "rule_review", "payload": {"rule_line": "x"}},
                {"decided_at": at(WED, 1), "source": "loopware", "action": "rule_accept", "surface": "rule_review", "payload": {"book_applied_at": "t"}}]
        s = st.build_status(rows, now=WED, candidates_meta={}, pending_desk=None)
        self.assertEqual(s["rules_pending_apply"], 1)


if __name__ == "__main__":
    unittest.main()
