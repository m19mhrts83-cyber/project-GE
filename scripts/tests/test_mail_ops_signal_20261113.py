"""#ops のメール系の色を中身で決める（2026-11-13 松野さん）。"""
import os
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_mail_ops_signal as ms  # noqa: E402

TODAY = date(2026, 11, 13)  # 金曜


def item(i, lane="general", kind="skim", days_ago=0, **kw):
    d = TODAY - timedelta(days=days_ago)
    return {
        "id": str(i), "lane": lane, "kind": kind, "status": "pending",
        "received_at": d.strftime("%Y/%m/%d 09:00"), **kw,
    }


class ClassifyTests(unittest.TestCase):
    def test_only_skim_and_notices_never_red(self):
        items = [item(i, days_ago=10) for i in range(200)]
        items += [item(900 + i, kind="mail", days_ago=10, from_email="info@vpass.ne.jp",
                       subject="【Vpass】ご利用のお知らせ", original_body="配信停止はこちら")
                  for i in range(50)]
        s = ms.classify(items, TODAY)
        self.assertEqual(s["level"], "yellow")
        self.assertEqual(s["stale"], [])
        self.assertEqual(s["skim"], 200)
        self.assertEqual(s["other"], 50)

    def test_old_partner_is_red(self):
        s = ms.classify([item(1, lane="partner", kind="mail", days_ago=4, partner="日本総険",
                              subject="12/24満期 火災保険")], TODAY)
        self.assertEqual(s["level"], "red")
        self.assertEqual(len(s["stale"]), 1)

    def test_fresh_partner_is_yellow(self):
        s = ms.classify([item(1, lane="partner", kind="mail", days_ago=1, partner="A")], TODAY)
        self.assertEqual(s["level"], "yellow")

    def test_weekend_not_counted(self):
        # 月曜朝に金曜の分 → 平日1日
        self.assertEqual(ms.weekdays_between(date(2026, 11, 13), date(2026, 11, 16)), 1)

    def test_human_general_mail_counts(self):
        h = item(1, kind="mail", days_ago=7, from_email="taro@gmail.com",
                 subject="ご相談", original_body="松野様\nお世話になります")
        self.assertEqual(ms.classify([h], TODAY)["level"], "red")

    def test_openchat_and_activity_ignored(self):
        s = ms.classify([item(1, lane="openchat", kind="chat", days_ago=9),
                         item(2, lane="partner", kind="activity", days_ago=9)], TODAY)
        self.assertEqual(s["level"], "green")

    def test_small_backlog_green(self):
        self.assertEqual(ms.classify([item(1, days_ago=1)], TODAY)["level"], "green")


class TextTests(unittest.TestCase):
    def test_daily_text_has_explicit_red_and_names(self):
        s = ms.classify([item(1, lane="partner", kind="mail", days_ago=6, partner="リリーフコミット",
                              subject="先日のお礼と確認事項について"),
                         item(2, days_ago=1)], TODAY)
        t = ms.daily_text(s, desk_url="https://x/desk")
        self.assertEqual(t.splitlines()[1][:5], "判定: 🔴")
        self.assertIn("リリーフコミット", t)
        self.assertIn("https://x/desk", t)

    def test_weekly_pick_three_to_five(self):
        items = [item(i, lane="partner", kind="mail", days_ago=i, partner=f"P{i}") for i in range(1, 9)]
        s = ms.classify(items, TODAY)
        with mock.patch.object(ms, "datetime") as dt:
            dt.now.return_value = datetime(2026, 11, 13, 5, 0)
            picks = ms.weekly_pick(s, items)
        self.assertEqual(len(picks), 5)
        self.assertEqual(picks[0]["partner"], "P8")  # 古い順

    def test_weekly_pick_fills_to_three(self):
        items = [item(1, lane="partner", kind="mail", days_ago=1, partner="A"),
                 item(2, kind="mail", days_ago=5, from_email="info@x.jp", original_body="配信停止"),
                 item(3, kind="mail", days_ago=3, from_email="info@y.jp", original_body="配信停止")]
        s = ms.classify(items, TODAY)
        self.assertEqual(len(ms.weekly_pick(s, items)), 3)


class ExpireTests(unittest.TestCase):
    def test_no_creds_no_expire(self):
        with mock.patch.dict(os.environ, {"JARVIS_SUPABASE_URL": "", "JARVIS_SUPABASE_SERVICE_ROLE_KEY": ""}):
            self.assertEqual(ms.expire_old_skim(), 0)

    def test_night_triage_local_skim_expires_at_7_days(self):
        import jarvis_night_triage as nt
        from zoneinfo import ZoneInfo

        now = datetime(2026, 11, 13, 5, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        items = [item(1, days_ago=8), item(2, days_ago=3), item(3, kind="mail", days_ago=8),
                 item(4, lane="partner", kind="mail", days_ago=22)]
        n = nt.expire_stale_pending(items, now=now)
        self.assertEqual(n, 2)
        self.assertEqual([i["status"] for i in items], ["skipped", "pending", "pending", "skipped"])


if __name__ == "__main__":
    unittest.main()
