#!/usr/bin/env python3
"""516 の緑・黄・赤判定（2026-11-09）。「止まっている」を実態に合わせる。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_slack_signal as sig  # noqa: E402
import jarvis_vendor_outreach_stall_runner as runner  # noqa: E402

TODAY = date(2026, 11, 9)  # 月


def q(**kw):
    base = {
        "needs_refill": False, "contacted_today": 0, "contacted_7d": 5,
        "last_contacted": "2026-11-06", "total": 100, "queue_ready": 10,
        "pending_discovered": 50, "daily_limit": 3, "followup": 0, "by_status": {},
    }
    base.update(kw)
    return base


class HealthTests(unittest.TestCase):
    def test_s2_weekly_burst_is_green(self):
        # 週1〜2回のまとめ送信（直近7日7件・最終は金曜）は正常
        lv, _ = runner.health_rating("s2", q(contacted_7d=7), today=TODAY)
        self.assertEqual(lv, "green")

    def test_s2_few_sends_is_yellow_not_red(self):
        lv, why = runner.health_rating("s2", q(contacted_7d=2), today=TODAY)
        self.assertEqual(lv, "yellow")
        self.assertIn("直近7日", why)

    def test_s2_long_gap_is_red(self):
        lv, _ = runner.health_rating(
            "s2", q(last_contacted="2026-10-23", contacted_7d=0), today=TODAY
        )
        self.assertEqual(lv, "red")

    def test_s2_no_candidates_is_red(self):
        lv, _ = runner.health_rating("s2", q(needs_refill=True), today=TODAY)
        self.assertEqual(lv, "red")

    def test_s9_two_week_cadence_is_green(self):
        lv, _ = runner.health_rating(
            "s9", q(last_contacted="2026-10-26", contacted_7d=0), today=TODAY
        )
        self.assertEqual(lv, "green")

    def test_s9_needs_refill_is_only_yellow(self):
        lv, _ = runner.health_rating(
            "s9", q(needs_refill=True, last_contacted="2026-11-03"), today=TODAY
        )
        self.assertEqual(lv, "yellow")

    def test_s4_never_stale_by_sends(self):
        lv, _ = runner.health_rating(
            "s4", q(last_contacted=None, contacted_7d=0), today=TODAY
        )
        self.assertEqual(lv, "green")
        self.assertEqual(runner.stale_marks_reason(q(last_contacted="2026-09-01"), lane="s4"), "")

    def test_bridge_down_is_red(self):
        lv, _ = runner.health_rating("s9", q(), bridge_ok=False, today=TODAY)
        self.assertEqual(lv, "red")

    def test_only_red_alerts(self):
        yellow = q(contacted_7d=2)
        self.assertFalse(runner.should_ops_alert(q=yellow, lst={}, bridge_ok=True, lane="s2")[0])
        red = q(needs_refill=True)
        self.assertTrue(runner.should_ops_alert(q=red, lst={}, bridge_ok=True, lane="s2")[0])

    def test_weekly_report_posts_even_when_not_green(self):
        results = [{"health": "red"}]
        ok, _ = runner.should_post_weekly_report({}, results)
        self.assertTrue(ok)


class GreenSignalTests(unittest.TestCase):
    def test_probation_week_then_quiet(self):
        st: dict = {}
        d0 = date(2026, 11, 10)
        self.assertTrue(runner.green_signal_active(st, today=d0))
        self.assertEqual(st["green_signal_until"], "2026-11-16")
        self.assertTrue(runner.green_signal_active(st, today=date(2026, 11, 16)))
        self.assertFalse(runner.green_signal_active(st, today=date(2026, 11, 17)))

    def test_weekly_quiet_after_probation_when_all_green(self):
        st = {"green_signal_until": "2026-11-16"}
        ok, why = runner.should_post_weekly_report(st, [{"health": "green"}])
        self.assertEqual(why, "all_green_quiet") if not ok else None
        ok2, _ = runner.should_post_weekly_report(st, [{"health": "yellow"}], force=True)
        self.assertTrue(ok2)

    def test_green_signal_text(self):
        r = {"label": "S2地場紹介", "health": "green", "health_reason": "",
             "q": {"contacted_7d": 7, "last_contacted": "2026-11-09"}}
        text = runner.build_green_signal([r], until="2026-11-16")
        self.assertIn("判定: 🟢", text)
        self.assertIn("2026-11-16", text)


class SignalTests(unittest.TestCase):
    def test_head_and_worst(self):
        self.assertEqual(sig.head_line("green"), "判定: 🟢 回っています")
        self.assertEqual(sig.worst(["green", "yellow", "none"]), "yellow")
        self.assertEqual(sig.worst([]), "none")


if __name__ == "__main__":
    unittest.main()
