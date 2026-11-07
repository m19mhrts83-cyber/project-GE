#!/usr/bin/env python3
"""判断ログ（owner_decisions）週次まとめと link-pending のテスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "tests"))

import jarvis_comm_hub as hub  # noqa: E402
import jarvis_owner_decisions_weekly as wk  # noqa: E402
from test_comm_hub import _FakeSB  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")


class WeeklySummaryTests(unittest.TestCase):
    def _rows(self):
        return [
            {"id": 1, "surface": "triage", "action": "sent", "lane": "partner", "source": "slack_link",
             "partner": "ミニテック", "subject": "エアコン", "ai_proposal": "お世話になっております。\n確認します。",
             "final_text": "お世話になっております。\n本日中に確認して折り返します。", "edited": True, "payload": {}},
            {"id": 2, "surface": "triage", "action": "skipped", "lane": "partner", "source": "dashboard_or_script",
             "partner": "LEAF", "subject": "請求書", "note": "対応不要", "payload": {}},
            {"id": 3, "surface": "todoist_313", "action": "close", "employee": "313", "source": "slack_button",
             "payload": {}},
            {"id": 4, "surface": "triage", "action": "sent", "lane": "general", "payload": {"slack_vr_action": {}},
             "ai_proposal": "a", "final_text": "a", "edited": False},
        ]

    def test_employee_mapping(self):
        rows = self._rows()
        self.assertEqual(wk.employee_of(rows[0]), "111+211")
        self.assertEqual(wk.employee_of(rows[2]), "313")
        self.assertEqual(wk.employee_of(rows[3]), "vendor")

    def test_edit_ratio(self):
        self.assertEqual(wk.edit_ratio("abc", "abc"), 0)
        self.assertIsNone(wk.edit_ratio(None, "x"))
        self.assertGreater(wk.edit_ratio("abc", "xyz"), 0.9)

    def test_summary_has_rates_and_examples(self):
        now = datetime.now(JST)
        md = wk.summarize(self._rows(), since=now - timedelta(days=7), until=now)
        self.assertIn("判断の件数: 4 件", md)
        self.assertIn("111 パートナー連絡整理係", md)
        self.assertIn("見送り率", md)
        self.assertIn("50%", md)  # partner: 1 見送り / 2 件
        self.assertIn("直して送った: ミニテック", md)
        self.assertIn("+本日中に確認して折り返します。", md)
        self.assertIn("見送り: LEAF｜請求書（理由: 対応不要）", md)

    def test_empty_week(self):
        now = datetime.now(JST)
        self.assertIn("判断ログがありません", wk.summarize([], since=now, until=now))


class LinkPendingTests(unittest.TestCase):
    def _sb(self):
        sb = _FakeSB()
        t = (datetime.now(JST) - timedelta(days=30)).strftime("%Y/%m/%d %H:%M")
        md_item = hub.item_from_md_entry(
            {"folder": "P102_ミニテック", "received_at": t, "channel": "相手から返信",
             "subject": "Re: 見積", "summary": "見積送付", "body": "見積を送ります",
             "partner_name": "ミニテック"},
            recent_cutoff=datetime.now(JST) - timedelta(days=14),
        )
        md_item["channel"] = "gmail"  # 実データの見出しは Gmail 判定される
        md_item["occurred_at"] = datetime.fromisoformat(md_item["occurred_at"]).astimezone(
            ZoneInfo("UTC")).isoformat()
        sb.db["comm_items"] = [{**md_item, "id": "uuid-md", "created_at": "2026-11-01"}]
        sb.db["triage_items"] = [
            {"id": "gha-p-1", "lane": "partner", "status": "pending", "comm_item_id": None,
             "folder": "P102_ミニテック", "partner": "ミニテック", "channel": "Gmail", "received_at": t,
             "subject": "Re: 見積", "summary": "別の要約", "original_body": "見積を送ります"},
            {"id": "gha-cw-2", "lane": "partner", "status": "pending", "comm_item_id": None,
             "folder": "P104_LEAF", "partner": "LEAF", "channel": "Chatwork",
             "received_at": (datetime.now(JST) - timedelta(days=3)).strftime("%Y/%m/%d %H:%M"),
             "subject": "", "summary": "入金確認", "original_body": "入金を確認しました"},
            {"id": "closed", "lane": "partner", "status": "sent", "comm_item_id": None,
             "folder": "P104_LEAF", "received_at": "2026/11/01 10:00"},
        ]
        return sb

    def test_dry_run_counts_without_writing(self):
        sb = self._sb()
        st = hub.link_pending(sb, apply=False)
        self.assertEqual(st, {"pending_unlinked": 2, "matched": 1, "created": 1, "skipped": 0})
        self.assertEqual(len(sb.db["comm_items"]), 1)
        self.assertIsNone(sb.db["triage_items"][0]["comm_item_id"])

    def test_apply_links_and_marks_needs_reply(self):
        sb = self._sb()
        hub.link_pending(sb, apply=True)
        tri = {r["id"]: r for r in sb.db["triage_items"]}
        self.assertEqual(tri["gha-p-1"]["comm_item_id"], "uuid-md")
        self.assertTrue(tri["gha-cw-2"]["comm_item_id"])
        self.assertIsNone(tri["closed"]["comm_item_id"])
        items = {r["id"]: r for r in sb.db["comm_items"]}
        self.assertEqual(items["uuid-md"]["work_status"], "needs_reply")  # 過去分 done → needs_reply
        new = items[tri["gha-cw-2"]["comm_item_id"]]
        self.assertEqual(new["external_id"], "triage:gha-cw-2")
        self.assertEqual(new["work_status"], "needs_reply")
        self.assertEqual(len(sb.db["comm_links"]), 2)
        # 2回目は何もしない
        self.assertEqual(hub.link_pending(sb, apply=True)["pending_unlinked"], 0)


class MigrationTests(unittest.TestCase):
    def test_trigger_never_blocks_status_update(self):
        sql = (REPO / "apps/jarvis-dashboard/supabase/migrations/20261107_owner_decisions.sql").read_text()
        self.assertIn("exception when others", sql)
        self.assertIn("after update of status on public.triage_items", sql)
        self.assertIn("revoke all on table public.owner_decisions from anon, authenticated", sql)


if __name__ == "__main__":
    unittest.main()
