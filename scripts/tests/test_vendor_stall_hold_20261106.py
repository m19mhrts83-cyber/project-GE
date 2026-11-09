#!/usr/bin/env python3
"""業者開拓 stall の S2・S9 停滞の再発防止（2026-11-06）の単体テスト（ネットワーク・Mac 不要）。

- 同じ社を送信再開で 2 回渡して mark が無ければ「保留」→ 次の社に進む（S9 福島土地 47 回ループ）
- S2 はバッチに載せた社を次のバッチに入れない（chubu-083〜085 の再掲）／フォーム先頭
- S2 は mark 停滞時に送信再開ではなく追加バッチ（`-r2`）を出す
- S9 候補: 台帳に電話のみで入っている社にメールが見つかったら経路を更新
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_kurashift_vendor_list as s2list  # noqa: E402
import jarvis_s9_candidates_apply as cand  # noqa: E402
import jarvis_vendor_outreach_stall_runner as runner  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc


class OfferHoldTests(unittest.TestCase):
    def test_same_day_counts_once(self):
        lst: dict = {}
        t = datetime(2026, 11, 6, 1, 0, tzinfo=UTC)
        runner.record_offers(lst, ["a"], via="send_resume", at=t)
        runner.record_offers(lst, ["a"], via="send_resume", at=t + timedelta(hours=6))
        self.assertEqual(lst["offers"]["a"]["count"], 1)
        self.assertEqual(runner.held_ids(lst, now=t + timedelta(hours=7)), set())

    def test_two_days_without_mark_is_held(self):
        lst: dict = {}
        t = datetime(2026, 11, 5, 1, 0, tzinfo=UTC)
        runner.record_offers(lst, ["fukushima"], via="send_resume", at=t)
        runner.record_offers(lst, ["fukushima"], via="send_resume", at=t + timedelta(days=1))
        self.assertEqual(
            runner.held_ids(lst, now=t + timedelta(days=1, hours=1)), {"fukushima"}
        )

    def test_hold_expires(self):
        lst: dict = {}
        t = datetime(2026, 11, 5, 1, 0, tzinfo=UTC)
        runner.record_offers(lst, ["x"], via="send_resume", at=t)
        runner.record_offers(lst, ["x"], via="send_resume", at=t + timedelta(days=1))
        later = t + timedelta(days=runner.OFFER_HOLD_DAYS + 2)
        self.assertEqual(runner.held_ids(lst, now=later), set())

    def test_s9_send_resume_skips_held_vendor(self):
        rows = [
            {"id": "fukushima", "name": "福島土地", "channel": "email", "status": "pending"},
            {"id": "narumi", "name": "ナルミ不動産", "channel": "email", "status": "pending"},
        ]
        with mock.patch.object(runner, "s9_next_pending", return_value=rows):
            picked = runner.s9_sendable_focus(1, exclude={"fukushima"})
        self.assertEqual([v["id"] for v in picked], ["narumi"])

    def test_held_consult_has_next_owner_lines(self):
        lst: dict = {"offers": {"f": {"count": 47}}}
        text = runner.build_held_consult("s9", [{"id": "f", "name": "福島土地", "channel": "email"}], lst)
        self.assertIn("福島土地", text)
        self.assertIn("次: 人判断のみ", text)
        self.assertIn("担当メモ", text)
        self.assertIn("橋渡し", text)


class S2BatchTests(unittest.TestCase):
    LEDGER = [
        {"id": "chubu-083", "name": "美濃善", "status": "pending", "channel": "web_form",
         "contact_url": "https://a.example/"},
        {"id": "mail-only", "name": "メールだけ", "status": "discovered", "channel": "email",
         "contact_url": "https://b.example/"},
        {"id": "fresh-form", "name": "新しいフォーム", "status": "pending", "channel": "web_form",
         "contact_url": "https://c.example/contact"},
    ]

    def _payload(self, **kw):
        with mock.patch.object(s2list, "load_list", return_value={"settings": {}, "vendors": self.LEDGER}), \
             mock.patch.object(s2list, "next_pending", side_effect=lambda limit: list(self.LEDGER)[:limit]), \
             mock.patch.object(s2list, "enrich_vendor", side_effect=lambda v: dict(v)), \
             mock.patch.object(s2list, "contacted_snapshot", return_value=([], [], [])), \
             mock.patch.object(s2list, "load_form_contact", return_value={"name": "x"}):
            return s2list.build_batch_week_payload(batch_days=1, **kw)

    def test_batch_excludes_previously_offered_and_puts_forms_first(self):
        p = self._payload(exclude_ids={"chubu-083"}, batch_id="2026-W45-r2")
        ids = [v["id"] for v in p["vendors"]]
        self.assertNotIn("chubu-083", ids)
        self.assertEqual(ids[0], "fresh-form")
        self.assertEqual(p["batch_id"], "2026-W45-r2")

    def test_batched_ids_window(self):
        lst: dict = {}
        now = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
        runner.record_offers(lst, ["old"], via="batch", at=now - timedelta(days=40))
        runner.record_offers(lst, ["w45"], via="batch", at=now - timedelta(days=4))
        self.assertEqual(runner.s2_batched_ids(lst, now=now), {"w45"})

    def test_next_batch_id_midweek(self):
        now = datetime(2026, 11, 6, 23, 0, tzinfo=JST)  # W45 金
        # 旧版で出した W45 バッチ（last_batch_id 記録なし）
        lst = {"last_refill_at": "2026-11-01T15:02:05+00:00"}
        self.assertEqual(runner.s2_next_batch_id(lst, now), "2026-W45-r2")
        lst = {"last_refill_at": "2026-11-06T14:00:00+00:00", "last_batch_id": "2026-W45-r2"}
        self.assertEqual(runner.s2_next_batch_id(lst, now), "2026-W45-r3")
        lst = {"last_refill_at": "2026-10-30T00:00:00+00:00", "last_batch_id": "2026-W44"}
        self.assertEqual(runner.s2_next_batch_id(lst, now), "2026-W45")


# 現在日時を固定（last_refill_at=2026-11-01 を「今週（W45）」とみなす。実行日に依存させない）
FROZEN_NOW = datetime(2026, 11, 6, 23, 0, tzinfo=JST)


class S2StaleUsesBatchTests(unittest.TestCase):
    """S2 停滞時は send_resume ではなく追加バッチを書く。"""

    def test_run_lane_s2_stale_writes_batch(self):
        q = {
            "lane": "s2", "phase": 2, "daily_limit": 3, "queue_ready": 21,
            "pending_discovered": 349, "needs_refill": False, "followup": 0,
            "contacted_today": 0, "last_contacted": "2026-11-03", "by_status": {},
            "total": 499, "extra": {},
        }
        state = {"lanes": {"s2": {"last_refill_at": "2026-11-01T15:02:05+00:00"}}}
        calls = {}

        def fake_refill(**kw):
            calls.update(kw)
            return {"ok": True, "batch_id": kw.get("batch_id"), "vendor_ids": ["fresh-form"]}

        with mock.patch.dict(runner.ASSESSORS, {"s2": lambda: q}), \
             mock.patch.object(runner, "bridge_available", return_value=True), \
             mock.patch.object(runner, "write_s2_refill", side_effect=fake_refill), \
             mock.patch.object(runner, "write_send_resume") as resume, \
             mock.patch.object(runner, "push_sync_meta"), \
             mock.patch.object(runner, "pending_vendors", return_value=[]), \
             mock.patch.object(runner, "business_days_between", return_value=6), \
             mock.patch.object(runner, "now_jst", return_value=FROZEN_NOW):
            r = runner.run_lane(
                "s2", dry=False, force_refill=False, skip_sync=True, skip_refill=False,
                state=state, inbox_hits=[], archive_inbox=False,
            )
        resume.assert_not_called()
        self.assertTrue(calls["batch_id"].endswith("-r2"))
        self.assertEqual(r["refill"]["mode"], "stale_refill")
        self.assertIn("fresh-form", state["lanes"]["s2"]["offers"])
        self.assertIn("追加バッチ", runner.build_ops_alert(r))


class S9CandidateUpgradeTests(unittest.TestCase):
    def test_phone_row_gets_email(self):
        existing = {"name": "有限会社ベストハウス", "status": "pending", "channel": "phone"}
        row = cand.to_row(
            {
                "heading": "有限会社ベストハウス",
                "社名": "有限会社ベストハウス",
                "所在": "名古屋市緑区鳴海町字京田105-2",
                "公式URL": "https://www.best-house.net/",
                "連絡経路": "メール info@best-house.net（会社概要に記載）",
            },
            md_date="2026-11-05",
        )
        self.assertIs(cand.find_existing(row, [existing]), existing)
        self.assertTrue(cand.upgrade_route(row, existing))
        self.assertEqual(existing["channel"], "email")
        self.assertEqual(existing["contact_email"], "info@best-house.net")

    def test_contacted_row_is_not_touched(self):
        existing = {"name": "X", "status": "contacted", "channel": "phone"}
        row = {"channel": "email", "contact_email": "a@b.jp", "source": "s"}
        self.assertFalse(cand.upgrade_route(row, existing))


if __name__ == "__main__":
    unittest.main()
