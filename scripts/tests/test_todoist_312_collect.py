#!/usr/bin/env python3
"""312 入口（jarvis_todoist_312_collect.py）の判定と3案のテスト（ネットワーク不要）。"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock
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

    def test_nody_url_without_key_goes_through_dashboard(self):
        # 投稿側に鍵が無いと素のリンクは Nody の /login で止まる → ダッシュ経由にする（2026-11-12）
        with mock.patch.dict(os.environ, {"LOOPWARE_ACCESS_KEY": "", "JARVIS_DASHBOARD_URL": ""}):
            url = c.nody_url("/312?topic=abc", NOW)
        self.assertEqual(url, "https://jarvis-dashboard-amber.vercel.app/go/loopware?to=/312%3Ftopic%3Dabc")

    def test_nody_url_with_key_has_pass(self):
        with mock.patch.dict(os.environ, {"LOOPWARE_ACCESS_KEY": "k", "JARVIS_LOOPWARE_URL": ""}):
            url = c.nody_url("/312?topic=abc", NOW)
        self.assertTrue(url.startswith("https://jarvis-loopware.vercel.app/312?topic=abc&t="), url)



# ---- 台帳（comm_items）からの入口 ------------------------------------------------
from unittest import mock  # noqa: E402


def _item(i, **kw):
    row = {
        "id": f"00000000-0000-0000-0000-00000000000{i}",
        "channel": "gmail",
        "account": "estate",
        "category": "inquiry",
        "direction": "inbound",
        "occurred_at": "2026-11-08T09:08:00+09:00",
        "subject": "空室のご相談",
        "summary": "見積りの確認をお願いしたい",
        "body_text": "",
        "work_status": "new",
        "context_header": "山田不動産｜y@example.jp｜gmail(estate)｜相手→自分｜2026-11-08 09:08",
        "source_ref": {"source": "triage_items", "account": "estate", "gmail_thread_id": "th1"},
    }
    row.update(kw)
    return row


class CommPick(unittest.TestCase):
    def test_new_inbound_is_picked(self):
        self.assertEqual(len(c.pick_comm([_item(1)], set(), set())), 1)

    def test_needs_reply_only_when_triage_pending(self):
        it = _item(2, work_status="needs_reply")
        self.assertEqual(c.pick_comm([it], set(), set()), [])  # 閉じ残し
        self.assertEqual(len(c.pick_comm([it], {it["id"]}, set())), 1)

    def test_done_and_known_are_skipped(self):
        self.assertEqual(c.pick_comm([_item(3, work_status="done")], set(), set()), [])
        it = _item(4)
        self.assertEqual(c.pick_comm([it], set(), {f"comm_items:{it['id']}"}), [])

    def test_auto_reply_skipped(self):
        self.assertEqual(c.pick_comm([_item(10, subject="お問い合わせありがとうございます（自動返信）")], set(), set()), [])

    def test_own_line_and_thanks_skipped(self):
        own = _item(11, channel="line", subject="(件名なし)", summary="", body_text="<details>\n<summary>本文</summary>\n\n2026/11/08 12:38  松野真治  資料を送ります")
        thanks = _item(12, channel="line", subject="(件名なし)", summary="", body_text="2026/11/08 12:38  岡田  いつもありがとうございます！")
        ask = _item(13, channel="line", subject="(件名なし)", summary="", body_text="2026/11/08 12:38  岡田  見積りを今週中にください")
        chat = _item(14, channel="line", subject="(件名なし)", summary="", body_text="2026/11/08 06:50  岡田  昨晩の地震は大丈夫でしたか、こちらは揺れました")
        talk = _item(15, channel="line", subject="(件名なし)", summary="", body_text="2026/11/08 06:50  岡田  自宅は被害ありませんでした")
        self.assertEqual([x["id"] for x in c.pick_comm([own, thanks, ask, talk], set(), set())], [ask["id"]])
        self.assertEqual(len(c.pick_comm([chat], set(), set())), 1)  # 問いかけは残る（判断は Nody で）
        self.assertEqual(c.comm_text(ask), "見積りを今週中にください")

    def test_chatwork_greeting_only_skipped_and_title_is_the_ask(self):
        cw = "<details>\n<summary>本文を開く</summary>\n\n松野真治さん\nCC：\nお疲れ様です。\nご対応ありがとうございます。\n\n(1)〜(5) すべて異存はございません。\nまた、エグゼ会員への先行展開ですが、\n来週中くらいに公開自体は可能でしょうか？\nロゴ_2 .png\n</details>\n\n**添付ファイル**: x.png"
        ask = _item(16, channel="chatwork", subject="松野真治さん CC： お疲れ様です。", summary="", body_text=cw)
        bye = _item(17, channel="chatwork", subject="かしこまりました", summary="", body_text="<details>\n<summary>本文を開く</summary>\n\nかしこまりました、\nご丁寧にありがとうございます♪\n</details>")
        add = _item(18, channel="chatwork", subject="追加ですみません", summary="", body_text="追加ですみません\nよろしくお願いします")
        got = c.pick_comm([ask, bye, add], set(), set())
        self.assertEqual([g["id"] for g in got], [ask["id"]])
        self.assertEqual(c.comm_text(ask), "また、エグゼ会員への先行展開ですが、来週中くらいに公開自体は可能でしょうか？")

    def test_own_form_and_handled_and_signoff_skipped(self):
        form = _item(19, channel="other", subject="空室対策のご相談", summary="", body_text="お世話になります。\n松野と申します。\n空室時の一般媒介のご相談先を探しております。ご検討ください",
                     source_ref={"path": "p", "channel_raw": "こちらから相談（HPフォーム）"})
        handled = _item(20, channel="other", subject="回答", summary="", body_text="回答あり。\n**対応**: 台帳に追加。ご確認ください")
        signoff = _item(21, channel="chatwork", subject="x", summary="", body_text="別途ご案内させていただきますので、よろしくお願いします")
        self.assertEqual(c.pick_comm([form, handled, signoff], set(), set()), [])

    def test_mail_greeting_summary_uses_subject_and_ask(self):
        it = _item(22, subject="山村不動産", summary="松野真治 様 山村不動産の山村と申します", body_text="松野真治 様\n山村不動産の山村と申します。\n先日の物件について、内見のご希望日を教えてください。")
        self.assertEqual(c.comm_text(it), "山村不動産｜先日の物件について、内見のご希望日を教えてください。")

    def test_chatwork_quote_and_tags_removed(self):
        body = "[qt][qtmeta aid=1 time=2]前の発言です。ご確認ください[/qt]\n[To:123]松野さん\nまた、Q&Aの公開日を教えてください"
        self.assertEqual(c.chat_ask_line(body), "また、Q&Aの公開日を教えてください")
        self.assertIsNone(c.chat_ask_line("宜しくお願いします"))

    def test_self_only_promise(self):
        yes = _item(5, category="self", direction="outbound", body_text="見積書は明日お送りします。\n\n> 以前のメール\n> 確認します")
        no = _item(6, category="self", direction="outbound", body_text="ありがとうございました。\n> 確認します")
        got = c.pick_comm([yes, no], set(), set())
        self.assertEqual([g["id"] for g in got], [yes["id"]])
        self.assertIn("お送りします", c.comm_text(yes))

    def test_origin_links_back(self):
        self.assertEqual(c.comm_origin(_item(7)), "https://mail.google.com/mail/u/matsuno.estate@gmail.com/#all/th1")
        md = _item(8, source_ref={"path": "215/P102/5.やり取り.md", "heading": "### 2026/11/08｜ミニテック"})
        self.assertTrue(c.comm_origin(md).startswith("215/P102/5.やり取り.md"))

    def test_comm_topic_shape(self):
        topic, props, info = c.comm_topic(_item(9), [], NOW)
        self.assertEqual(topic["source_kind"], "comm")
        self.assertEqual(topic["source_ref"], f"comm_items:{_item(9)['id']}")
        self.assertEqual(topic["comm_item_id"], _item(9)["id"])
        self.assertEqual([p["label"] for p in props], list(c.LABELS))
        self.assertNotIn("Slack", props[2]["body"])
        self.assertIn("相手：山田不動産", topic["topic_text"])


class SlackUnchanged(unittest.TestCase):
    """台帳を足しても Slack 由来の文面・反映は変わらない。"""

    def test_slack_proposals_text_unchanged(self):
        props = c.build_proposals(text=REAL_315, kind="request", permalink="https://x/p1", when="11/2 9:00", match=None, now=NOW)
        self.assertIn("説明：Slack の依頼から起票。", props[2]["body"])
        m = {"id": "1", "content": "315 健全化", "due": {"date": "2026-11-20"}}
        p2 = c.build_proposals(text=REAL_315, kind="request", permalink="https://x/p1", when="11/2 9:00", match=m, now=NOW)[1]["body"]
        self.assertIn("追記文：11/2 9:00 の Slack で松野さんから依頼あり。", p2)

    def test_consult_lines_without_comm_unchanged(self):
        made = [{"kind": "request", "title": "315 健全化", "link": "https://x/p1"}]
        self.assertEqual(
            c.consult_lines(made, []),
            ["【相談】312 Todoist起票整理｜起票候補 1件", "", "1. [依頼] 315 健全化  <https://x/p1|元の発言>"],
        )

    def test_consult_lines_with_comm(self):
        made = [{"kind": "request", "title": "315 健全化", "link": "https://x/p1"}]
        comm = [{"label": "メール", "title": "空室のご相談", "link": "https://mail.google.com/x"}]
        lines = c.consult_lines(made, comm)
        self.assertEqual(lines[0], "【相談】312 Todoist起票整理｜起票候補 2件（Slack 1件・メール等 1件）")
        self.assertEqual(lines[3], "2. [メール] 空室のご相談  <https://mail.google.com/x|元のメール>")

    def _reflect(self, topic):
        calls = []

        def fake_sb(path, params=None, method="GET", body=None, prefer=""):
            calls.append((path, method, params, body))
            if path == "task_loop_decisions" and method == "GET":
                return [{"id": "d1", "topic_id": "t1", "choice": "use", "chosen_index": 3, "final_text": None}]
            if path == "task_loop_topics":
                return [topic]
            if path == "task_loop_proposals":
                return [{"topic_id": "t1", "proposal_index": 3, "label": "別タスクを作る", "body": "タイトル：空室の相談\n期限：記載なし"}]
            if path == "comm_items" and method == "GET":
                return [{"id": "c1", "account": "estate", "source_ref": {"account": "estate", "gmail_thread_id": "th1"}}]
            return []

        todo = []

        def fake_todoist(path, method="GET", body=None):
            todo.append((path, body))
            return {"id": "T9"} if path == "tasks" else {}

        with mock.patch.object(c, "sb", side_effect=fake_sb), mock.patch.object(c, "todoist", side_effect=fake_todoist):
            c.reflect(dry=False)
        return calls, todo

    def test_reflect_slack_topic_unchanged(self):
        calls, todo = self._reflect({"id": "t1", "source_kind": "slack", "source_ref": "https://slack/p1", "todoist_task_ids": [], "topic_text": "x"})
        self.assertIn("出典: https://slack/p1", todo[0][1]["description"])
        self.assertFalse(any(p in ("comm_items", "comm_links") for p, *_ in calls))
        topics_q = [prm for p, m, prm, _ in calls if p == "task_loop_topics"][0]
        self.assertEqual(topics_q["source_kind"], "in.(slack,comm)")

    def test_reflect_comm_topic_links_back(self):
        calls, todo = self._reflect(
            {"id": "t1", "source_kind": "comm", "source_ref": "comm_items:c1", "comm_item_id": "c1", "todoist_task_ids": [], "topic_text": "x"}
        )
        self.assertIn("出典: https://mail.google.com/mail/u/matsuno.estate@gmail.com/#all/th1", todo[0][1]["description"])
        links = [b for p, m, _, b in calls if p == "comm_links" and m == "POST"]
        self.assertEqual(links[0]["target_type"], "todoist_task")
        self.assertEqual(links[0]["target_id"], "T9")
        patch = [(prm, b) for p, m, prm, b in calls if p == "comm_items" and m == "PATCH"][0]
        self.assertEqual(patch[1], {"work_status": "waiting"})
        self.assertEqual(patch[0]["work_status"], "in.(new,needs_reply)")


class CommSwitch(unittest.TestCase):
    def test_off_by_default_and_wednesday_only(self):
        with mock.patch.object(c, "comm_candidates") as cc, mock.patch.object(c, "active_tasks", return_value=[]), \
             mock.patch.object(c, "slack_messages", return_value=[]), mock.patch.object(c, "sb", return_value=[]):
            c.collect(hours=1, max_items=5, dry=True, now=NOW)  # 既定 comm_max=0
            cc.assert_not_called()
            c.collect(hours=1, max_items=5, dry=True, now=NOW, comm_max=5)  # NOW は月曜
            cc.assert_not_called()
            wed = NOW + timedelta(days=2)
            cc.return_value = []
            c.collect(hours=1, max_items=5, dry=True, now=wed, comm_max=5)
            cc.assert_called_once()

    def test_comm_failure_does_not_stop_slack(self):
        wed = NOW + timedelta(days=2)
        with mock.patch.object(c, "comm_candidates", side_effect=RuntimeError("db down")), \
             mock.patch.object(c, "active_tasks", return_value=[]), mock.patch.object(c, "slack_messages", return_value=[]), \
             mock.patch.object(c, "sb", return_value=[]):
            self.assertEqual(c.collect(hours=1, max_items=5, dry=True, now=wed, comm_max=5), 0)


if __name__ == "__main__":
    unittest.main()
