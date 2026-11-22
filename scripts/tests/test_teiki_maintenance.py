"""テイチャンのメンテ停止中の扱い（614 D4・2026-11-23）。値はすべて架空。"""
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

try:  # CI には playwright が無い。画面操作は使わないので空の型だけ用意する
    import playwright.sync_api  # noqa: F401
except ImportError:
    pw = types.ModuleType("playwright")
    sync = types.ModuleType("playwright.sync_api")
    sync.Page = object
    sync.sync_playwright = lambda: None
    pw.sync_api = sync
    sys.modules["playwright"] = pw
    sys.modules["playwright.sync_api"] = sync

import jarvis_morning_mac_refresh as mr  # noqa: E402
import jarvis_points_rebate_slack_report as sr  # noqa: E402
import jarvis_teiki_barai_chance as tb  # noqa: E402

MAINT_TEXT = (
    "定期払いチャンス\n"
    "システムメンテナンスにより、サービスを一時的に停止しております。\n"
    "サービス再開時期が決まり次第、お知らせいたします。\n"
)


def _iso(days_ago: float) -> str:
    return (datetime.now(tb.JST) - timedelta(days=days_ago)).isoformat(timespec="seconds")


class DetectTest(unittest.TestCase):
    def test_maintenance_detected_with_note(self):
        r = tb.detect_site_status(MAINT_TEXT)
        self.assertEqual(r["site_status"], "maintenance")
        self.assertIn("再開", r["maintenance_note"])

    def test_normal_page_not_maintenance(self):
        r = tb.detect_site_status("今月の抽選券 2 枚\nログアウト\nお支払い履歴")
        self.assertEqual(r["site_status"], "normal")

    def test_word_alone_is_not_enough(self):
        # 『メンテナンス』だけ（停止の文言なし）は停止中と決めつけない
        self.assertEqual(tb.detect_site_status("メンテナンス情報はこちら")["site_status"], "normal")


class DueTest(unittest.TestCase):
    def test_normal_with_tickets_is_due_immediately(self):
        st = {"last_check_at": _iso(0.1), "ticket_count": 2, "interval_days": 3}
        self.assertEqual(tb.is_due(st), (True, "tickets_pending"))

    def test_maintenance_ignores_stale_tickets_within_3_days(self):
        st = {"last_check_at": _iso(1), "ticket_count": 2, "interval_days": 3, "site_status": "maintenance"}
        due, reason = tb.is_due(st)
        self.assertFalse(due)
        self.assertTrue(reason.startswith("wait_"))

    def test_maintenance_due_after_3_days(self):
        st = {"last_check_at": _iso(3.1), "ticket_count": 2, "site_status": "maintenance"}
        self.assertTrue(tb.is_due(st)[0])

    def test_morning_catchup_follows_same_rule(self):
        def needs(st):
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "t.json"
                import json

                p.write_text(json.dumps(st), encoding="utf-8")
                with mock.patch.object(mr, "TEIKI_BARAI_STATE", p), \
                     mock.patch.dict("os.environ", {"JARVIS_TEIKI_BARAI_DISABLE": ""}):
                    return mr.teiki_draw_needs_catchup()

        base = {"ticket_count": 2, "w_chance_tickets": 0, "interval_days": 3}
        self.assertTrue(needs({**base, "last_check_at": _iso(0.5)}))  # 通常: 券>0 で起動（従来どおり）
        self.assertFalse(needs({**base, "last_check_at": _iso(0.5), "site_status": "maintenance"}))
        self.assertFalse(needs({**base, "last_check_at": _iso(2.5), "site_status": "maintenance"}))
        self.assertTrue(needs({**base, "last_check_at": _iso(3.2), "site_status": "maintenance"}))


class FakePage:
    url = "https://teikibarai.example/gift_info"

    def __init__(self, text):
        self._text = text
        self.clicked = False

    def inner_text(self, _sel):
        return self._text

    def screenshot(self, **_kw):
        pass

    def locator(self, *_a, **_kw):  # 操作が呼ばれたら失敗させる（停止中は何も押さない）
        self.clicked = True
        raise AssertionError("メンテ画面で画面操作をしてはいけない")

    def goto(self, *_a, **_kw):
        self.clicked = True
        raise AssertionError("メンテ画面で遷移してはいけない")


class ScrapeTest(unittest.TestCase):
    def test_maintenance_screen_returns_without_touching_page(self):
        with mock.patch.object(tb, "_shot", lambda *a, **k: None):
            page = FakePage(MAINT_TEXT)
            r = tb.scrape_and_maybe_draw(page, do_draw=True)
        self.assertEqual(r["site_status"], "maintenance")
        self.assertIsNone(r["ticket_count"])
        self.assertIsNone(r["draw"])
        self.assertFalse(page.clicked)


class StateTest(unittest.TestCase):
    def test_maintenance_keeps_old_ticket_count_and_records_status(self):
        st = {"ticket_count": 2, "enrolled": "yes"}
        tb.apply_scrape_to_state(
            st, {"site_status": "maintenance", "maintenance_note": "再開は決まり次第", "ticket_count": None}
        )
        self.assertEqual(st["ticket_count"], 2)
        self.assertEqual(st["enrolled"], "yes")
        self.assertEqual(st["site_status"], "maintenance")
        self.assertIn("maintenance_since", st)
        since = st["maintenance_since"]
        tb.apply_scrape_to_state(st, {"site_status": "maintenance", "maintenance_note": "x"})
        self.assertEqual(st["maintenance_since"], since)  # 開始日は変えない

    def test_resume_returns_to_normal(self):
        st = {"site_status": "maintenance", "maintenance_since": _iso(10), "ticket_count": 2}
        tb.apply_scrape_to_state(
            st, {"site_status": "normal", "ticket_count": 3, "w_chance_tickets": 0, "enrolled": "yes"}
        )
        self.assertEqual(st["site_status"], "normal")
        self.assertNotIn("maintenance_since", st)
        self.assertIn("maintenance_ended_at", st)
        self.assertEqual(st["ticket_count"], 3)
        self.assertIn("ticket_count_confirmed_at", st)

    def test_login_incomplete_does_not_change_site_status(self):
        st = {"site_status": "maintenance"}
        tb.apply_scrape_to_state(st, {"login_incomplete": True})
        self.assertEqual(st["site_status"], "maintenance")


class SlackTest(unittest.TestCase):
    def _t(self, **kw):
        base = dict(outcome="maintenance", tickets=2, w_chance=0, enrolled="yes", drew_summary="",
                    reason="", error="", note="", last_check="11/23", maintenance_note="")
        base.update(kw)
        return sr.build_teiki(**base)

    def test_maintenance_text(self):
        t = self._t()
        self.assertIn("メンテナンス停止中（最終確認 11/23）", t)
        self.assertNotIn("確認のみ", t)
        self.assertNotIn("券=", t)

    def test_checked_unchanged(self):
        t = self._t(outcome="checked")
        self.assertIn("確認のみ（抽選なし）", t)
        self.assertIn("券=2枚", t)


class LockTest(unittest.TestCase):
    def test_second_lock_fails_until_released(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "run.lock"
            fd = tb.acquire_run_lock(p)
            self.assertIsNotNone(fd)
            self.assertIsNone(tb.acquire_run_lock(p))
            fd.close()
            fd2 = tb.acquire_run_lock(p)
            self.assertIsNotNone(fd2)
            fd2.close()


if __name__ == "__main__":
    unittest.main()
