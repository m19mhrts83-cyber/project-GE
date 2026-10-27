#!/usr/bin/env python3
"""業者開拓 stall の詰まり修正（2026-10-27）の単体テスト（ネットワーク・Mac 不要）。

- S9: 送信再開／補給は優先レーン（緑区）のメール・フォーム候補だけを渡す
- S9: 電話・面談で接触済の同じ店舗のフォーム行は二重接触として除く
- S2: ISO 週が替わったら週次バッチを出す
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_kurashift_mgmt_vendor_list as mgmt  # noqa: E402
import jarvis_vendor_outreach_stall_runner as runner  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")

LEDGER = [
    {"id": "kita-fc", "name": "賃貸住宅サービスFC名古屋店", "area": "愛知 名古屋市 名古屋駅",
     "property_lane": "kita_shiga", "status": "pending", "channel": "web_form",
     "contact_url": "https://example.com/fc-nagoya/form"},
    {"id": "kita-fc-met", "name": "賃貸住宅サービスFC名古屋店", "area": "愛知 名古屋市 名古屋駅",
     "property_lane": "kita_shiga", "status": "contacted", "channel": "phone",
     "precheck_sent_at": "2025-11-09"},
    {"id": "midori-phone", "name": "緑区 電話だけ不動産", "area": "名古屋市緑区",
     "property_lane": "midori_caramel", "status": "pending", "channel": "phone"},
    {"id": "midori-mail", "name": "緑区 メール不動産", "area": "名古屋市緑区",
     "property_lane": "midori_caramel", "status": "pending", "channel": "email",
     "contact_email": "info@midori-mail.example.jp"},
]


class MgmtDuplicateTests(unittest.TestCase):
    def test_same_store_contacted_by_phone_is_duplicate(self):
        why = mgmt.duplicate_contact_reason(LEDGER[0], LEDGER, contacted_only=True)
        self.assertIn("接触済", why)

    def test_different_store_is_not_duplicate(self):
        other = {**LEDGER[0], "name": "賃貸住宅サービス FC名古屋セントラルパーク店", "area": "愛知 名古屋市 千種駅"}
        self.assertEqual(mgmt.duplicate_contact_reason(other, LEDGER, contacted_only=True), "")

    def test_next_pending_skips_duplicate_store(self):
        with mock.patch.object(mgmt, "load_list", return_value={"vendors": [dict(v) for v in LEDGER]}), \
             mock.patch.object(mgmt, "load_share_urls", return_value={}):
            ids = [v["id"] for v in mgmt.next_pending(limit=10)]
        self.assertNotIn("kita-fc", ids)


class S9FocusTests(unittest.TestCase):
    def _pending(self, *, limit, lane=None, balanced=False, stats=None):
        rows = [v for v in LEDGER if v["status"] == "pending"]
        if lane:
            rows = [v for v in rows if v["property_lane"] == lane]
        return rows[:limit]

    def test_focus_lane_only_sendable(self):
        with mock.patch.dict(os.environ, {"JARVIS_S9_FOCUS_LANE": "midori_caramel"}), \
             mock.patch.object(runner, "s9_next_pending", side_effect=self._pending):
            ids = [v["id"] for v in runner.s9_sendable_focus(1)]
        self.assertEqual(ids, ["midori-mail"])

    def test_refill_skips_when_focus_has_nothing_sendable(self):
        with mock.patch.dict(os.environ, {"JARVIS_S9_FOCUS_LANE": "midori_caramel"}), \
             mock.patch.object(runner, "s9_next_pending", return_value=[LEDGER[2]]):
            out = runner.write_s9_refill(dry_run=True)
        self.assertFalse(out["ok"])
        self.assertTrue(out["skipped"])


class S2WeeklyRolloverTests(unittest.TestCase):
    def test_new_iso_week_is_due(self):
        # W43 の土曜に出したバッチ → W44 の火曜
        now = datetime(2026, 10, 27, 9, 0, tzinfo=JST)
        self.assertTrue(runner.s2_weekly_rollover_due("2026-10-24T01:52:31+00:00", now))

    def test_same_week_is_not_due(self):
        now = datetime(2026, 10, 29, 9, 0, tzinfo=JST)
        self.assertFalse(runner.s2_weekly_rollover_due("2026-10-26T00:30:00+00:00", now))

    def test_never_refilled_is_due(self):
        self.assertTrue(runner.s2_weekly_rollover_due(None))


if __name__ == "__main__":
    unittest.main()
