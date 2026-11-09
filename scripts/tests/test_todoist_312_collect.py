#!/usr/bin/env python3
"""312 入口（jarvis_todoist_312_collect.py）の判定と3案のテスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_todoist_312_collect as c  # noqa: E402

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 9, 20, 30, tzinfo=JST)
OWNER = "U0C7X79N4P7"

# 11/2 #consult の実発言（取りこぼしの例）
REAL_315 = "todoistへ追加して。315健全化依頼します。11/1にcodexで確認したらLineオプチャ取得成功報告を受けているから話が整合していない懸念がある"
# 毎朝の #report 日次（AI が出す報告）
DAILY_REPORT = "【日次】11/5\n場所: Todoist「AIエージェントチーム」\n列件数: 確認1／進行9／未着手5／HOLD23\n\n今日見る→同PJの「オーナー確認」列\n1. [312] 起票整理の具体化…"


def msg(text: str, **kw) -> dict:
    return {"user": OWNER, "text": text, "ts": "1793547535.618959", **kw}


class HumanLike(unittest.TestCase):
    def test_real_request_passes(self):
        self.assertTrue(c.is_human_like(msg(REAL_315), OWNER))
        self.assertEqual(c.classify(REAL_315), "request")

    def test_daily_report_is_excluded(self):
        self.assertFalse(c.is_human_like(msg(DAILY_REPORT), OWNER))

    def test_ai_posts_as_owner_are_excluded(self):
        for t in [
            "【Grok定型報告】不動産 本日分 11/2（月）部長ラン",
            "[Jarvis依頼] 不動産部長 本日分 2026-11-02",
            ":pushpin:要ボス\n• 犬山鳥屋越520万の第一問合せ送信を進めてよいか",
            "是正しました。\n記録者: Jarvis Cloud · 2026-10-18",
        ]:
            self.assertFalse(c.is_human_like(msg(t), OWNER), t)

    def test_bot_and_other_users_are_excluded(self):
        self.assertFalse(c.is_human_like(msg(REAL_315, bot_id="B1"), OWNER))
        self.assertFalse(c.is_human_like({**msg(REAL_315), "user": "U999"}, OWNER))
        self.assertFalse(c.is_human_like(msg("了解です"), OWNER))

    def test_done_reaction(self):
        self.assertTrue(c.has_done_reaction(msg(REAL_315, reactions=[{"name": "white_check_mark"}])))
        self.assertFalse(c.has_done_reaction(msg(REAL_315, reactions=[{"name": "eyes"}])))


class Classify(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(c.classify("312の件、どうなってますか？"), "question")
        self.assertEqual(c.classify("Grok bot とも連携できるようにしたいですね"), "wish")
        self.assertIsNone(c.classify("今日は雨ですね"))


class Title(unittest.TestCase):
    def test_lead_words_are_dropped(self):
        self.assertEqual(c.derive_title(REAL_315), "315健全化依頼します")

    def test_due(self):
        self.assertEqual(c.parse_due("見積書を11月12日までに", NOW), "2026-11-12")
        self.assertEqual(c.parse_due("1/10までに出す", NOW), "2027-01-10")
        self.assertIsNone(c.parse_due("11/1にcodexで確認", NOW))


class Match(unittest.TestCase):
    TASKS = [
        {"id": "a", "content": "[315] 連携健全性点検係｜フロー確認→Automation→最終確認→プロンプト"},
        {"id": "b", "content": "[312] 起票整理の具体化 — Slack宿題も候補に載せる"},
        {"id": "c", "content": "確定申告の書類をそろえる"},
    ]

    def test_agent_number_pulls_match(self):
        m, _ = c.best_match(REAL_315, self.TASKS)
        self.assertEqual(m and m["id"], "a")

    def test_no_match(self):
        m, _ = c.best_match("Grok bot とも連携できるようにしたい", self.TASKS[2:])
        self.assertIsNone(m)


class Proposals(unittest.TestCase):
    def test_three_cards_one_star_in_order(self):
        match = {"id": "a", "content": "[315] 連携健全性点検係", "due": None}
        props = c.build_proposals(text=REAL_315, kind="request", permalink="https://x/p1", when="11/2 00:38", match=match, now=NOW)
        self.assertEqual([p["label"] for p in props], list(c.LABELS))
        self.assertEqual(sum(p["is_starred"] for p in props), 1)
        self.assertIn("https://x/p1", props[2]["body"])
        self.assertEqual(c.parse_body(props[2]["body"])["タイトル"], "315健全化依頼します")
        self.assertEqual(c.parse_body(props[1]["body"])["対象"], "[315] 連携健全性点検係")

    def test_no_match_append_card_says_so(self):
        props = c.build_proposals(text="Grok連携を進めたい", kind="wish", permalink="https://x/p2", when="11/9 10:00", match=None, now=NOW)
        self.assertIn("見つかりません", props[1]["body"])
        self.assertTrue(props[0]["is_starred"])


class LinkToken(unittest.TestCase):
    def test_shape_matches_access_ts(self):
        tok = c.link_token("k", NOW)
        exp, sig = tok.split(".")
        self.assertEqual(int(exp), int(NOW.timestamp()) + 7 * 86400)
        self.assertRegex(sig, r"^[A-Za-z0-9_-]{20,}$")


if __name__ == "__main__":
    unittest.main()
