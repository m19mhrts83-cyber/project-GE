#!/usr/bin/env python3
"""機械の予備（jarvis_comm_hub_backup）と heartbeat のテスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import jarvis_comm_hub as hub  # noqa: E402
import jarvis_comm_hub_backup as bk  # noqa: E402
from test_comm_hub import _FakeSB  # noqa: E402

UTC = ZoneInfo("UTC")
JST = ZoneInfo("Asia/Tokyo")


def hb(at: datetime, source: str = "gha") -> dict:
    return {"at": at.astimezone(UTC), "source": source}


class DecideTests(unittest.TestCase):
    now = datetime(2026, 11, 11, 13, 40, tzinfo=JST)

    def test_all_fresh_does_nothing(self):
        acts = bk.decide(self.now, hb(self.now - timedelta(hours=2)), hb(self.now - timedelta(hours=1)), None)
        self.assertEqual(acts, [])

    def test_stale_write_runs_link_pending_and_reconcile(self):
        acts = bk.decide(self.now, hb(self.now - timedelta(hours=20)), hb(self.now - timedelta(days=1)), None)
        self.assertEqual(acts, ["link_pending", "reconcile"])

    def test_very_stale_alerts_once_a_day(self):
        old = hb(self.now - timedelta(hours=30))
        self.assertIn("alert", bk.decide(self.now, old, None, None))
        self.assertNotIn("alert", bk.decide(self.now, old, None, hb(self.now - timedelta(hours=1))))
        self.assertIn("alert", bk.decide(self.now, old, None, hb(self.now - timedelta(days=1))))

    def test_no_heartbeat_at_all(self):
        self.assertEqual(bk.decide(self.now, None, None, None), ["link_pending", "reconcile", "alert"])

    def test_reconcile_waits_until_afternoon(self):
        morning = datetime(2026, 11, 11, 9, 0, tzinfo=JST)
        acts = bk.decide(morning, hb(morning - timedelta(hours=2)), None, None)
        self.assertEqual(acts, [])

    def test_alert_text_mentions_next_step(self):
        t = bk.alert_text(None)
        self.assertIn("記録なし", t)
        self.assertIn("comm_write", t)
        self.assertEqual(len(t.splitlines()), 3)


class HeartbeatTests(unittest.TestCase):
    def test_write_then_read(self):
        sb = _FakeSB()
        at = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)
        hub.write_heartbeat(sb, "comm_write", "backup", now=at)
        hub.write_heartbeat(sb, "comm_write", "backup", now=at + timedelta(hours=1))  # 上書き
        self.assertEqual(len(sb.db["sync_meta"]), 2)  # 偽DBは upsert で積む → 先頭を読む
        r = hub.read_heartbeat(sb, "comm_write")
        self.assertEqual(r["source"], "backup")
        self.assertEqual(r["at"], at)
        self.assertIsNone(hub.read_heartbeat(sb, "reply_211"))

    def test_reads_gha_finish_format(self):
        sb = _FakeSB()
        sb.db["sync_meta"] = [
            {"key": "job_ok:comm_write", "value": '{"at":"2026-11-11T02:33:00Z","source":"gha:banto","run":"u"}'}
        ]
        r = hub.read_heartbeat(sb, "comm_write")
        self.assertEqual(r["at"], datetime(2026, 11, 11, 2, 33, tzinfo=UTC))
        self.assertEqual(hub._source_label(r["source"]), "窓口・banto")

    def test_slack_text_three_lines(self):
        c = {"a": 6, "b": 6, "b_general": 3, "needs_reply_total": 9, "a_unlinked": 0, "stale": 0, "unlinked": 0, "reverse": 0}
        t = hub.reconcile_slack_text(c, source="gha", last_write=hb(datetime(2026, 11, 11, 2, 33, tzinfo=UTC)))
        lines = t.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("台帳 ✅", lines[0])
        self.assertIn("一致", lines[0])
        self.assertIn("11/11 11:33（GHA）", lines[2])
        c["reverse"] = 1
        self.assertIn("⚠️", hub.reconcile_slack_text(c, source="backup", last_write=None))


if __name__ == "__main__":
    unittest.main()
