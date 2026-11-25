from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_todoist_cleanup_bulk as b  # noqa: E402

TODAY = date(2026, 11, 17)
NOW = datetime(2026, 11, 17, 8, 0, tzinfo=timezone(timedelta(hours=9)))


def task(i, content, desc="", **kw):
    return {"id": str(i), "content": content, "description": desc, "labels": kw.pop("labels", ["スター起票"]), **kw}


DESC = "送信者：Bybit\n件名：強制決済\n日付：2026-07-10\n要件：残高を確認。※期限は経過済み。\nhttps://mail.google.com/mail/u/0/#all/abc\n起票元：スター付きメール"


class CleanupBulkTests(unittest.TestCase):
    def test_parse(self):
        p = b.parse_description(DESC)
        self.assertEqual(p["sender"], "Bybit")
        self.assertEqual(p["mail_date"], "2026-07-10")
        self.assertTrue(p["gmail_url"].startswith("https://mail.google.com/"))

    def test_suggest(self):
        self.assertEqual(b.suggest("残高を確認", b.parse_description(DESC))[0], "close")
        promo = b.parse_description("送信者：X\n件名：セミナーのご案内\n要件：イベント案内。")
        self.assertEqual(b.suggest("内容を確認", promo)[0], "drop")
        money = b.parse_description("送信者：X\n件名：Re\n要件：入金されたか確認する。")
        self.assertEqual(b.suggest("着金を確認", money)[0], "keep")

    def test_snapshot_filters(self):
        tasks = [
            task(1, "A", DESC, due={"date": "2026-11-16"}),
            task(2, "B", DESC, due={"date": "2026-11-20"}),  # 日を変えた → まだ出さない
            task(3, "C", DESC, labels=["他"]),
            task(4, "D", DESC, due={"date": "2026-11-17"}),  # 残すで保留
            task(5, "E", DESC, parent_id="1"),
            task(6, "F", DESC, checked=True),
        ]
        s = b.build_snapshot(tasks=tasks, held={"4"}, today=TODAY, now=NOW)
        self.assertEqual([c["id"] for c in s["cards"]], ["1"])
        self.assertEqual(s["cards"][0]["age_days"], 130)

    def test_leak_queue_cards_get_leak_origin(self):
        now = datetime.now(b.JST)
        q = {"published": True, "generated_at": now.isoformat(), "cards": [{"id": "9", "title": "x", "suggest": "close"}]}
        out = b.merge_313_cards([], q, active_by_id={"9": {"id": "9", "content": "実タイトル"}}, held=set(), now=now, origin="leak")
        self.assertEqual([(c["id"], c["origin"], c["title"]) for c in out], [("9", "leak", "実タイトル")])
        self.assertEqual(b.merge_313_cards([], q, active_by_id={}, held=set(), now=now, origin="leak"), [])


if __name__ == "__main__":
    unittest.main()
