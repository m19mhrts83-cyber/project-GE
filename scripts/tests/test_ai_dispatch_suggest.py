import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_ai_dispatch_suggest as d

NOW = datetime(2026, 11, 10, 1, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def rep(codex=92, claude=7, cursor=51, gencode=100, chatgpt=None, claude_day="2026-11-09T12:45:13+09:00"):
    return {"period": {"since": "2026-11-03T00:00:00+09:00", "until": "2026-11-10T00:00:00+09:00"},
            "tools": {"codex": {"limits_latest": {"weekly": {"used_pct": codex, "resets_at": "2026-11-12T21:05:51+09:00"}}},
                      "claude_plan": {"pct": claude, "updated_at": claude_day},
                      "cursor": {"pct": cursor, "fetch_source": "auto", "auto_fetched_at": "2026-11-09T23:00:00+0900"},
                      "gencode": {"pct": gencode, "updated_at": "2026-11-10T00:37:42+09:00", "note": "クレジット切れ"},
                      "chatgpt_mode": {"pct": chatgpt}}}


def task_md(tmp, body):
    p = Path(tmp) / "TASK.md"
    p.write_text(body, encoding="utf-8")
    return d.read_task(p)


def one(task, r=None, kind=None):
    return d.build([task], kind, r or rep(), NOW)["items"][0]


class DispatchTests(unittest.TestCase):
    def test_implement_goes_to_most_room_and_skips_blocked(self):
        it = one({"title": "814 点検の画面別判定を実装", "text": "スクリプトを実装"})
        self.assertEqual(it["decision"]["agent"], "claude_code")
        ex = "、".join(it["decision"]["excluded"])
        self.assertIn("Codex（92% で逼迫）", ex)
        self.assertIn("フライデー（クレジット切れ）", ex)

    # 1. まとめて出すと分散する
    def test_batch_spreads_load(self):
        tasks = [{"title": f"実装{i}", "text": "実装"} for i in range(4)]
        res = d.build(tasks, None, rep(codex=40, claude=30, cursor=45, gencode=100), NOW)
        who = [it["decision"]["agent"] for it in res["items"]]
        self.assertGreater(len(set(who)), 1)
        self.assertEqual(who[0], "claude_code")

    # 2. 実行中・定期は振り直さない
    def test_running_and_routine_are_kept(self):
        with tempfile.TemporaryDirectory() as t:
            run = task_md(t, "# TASK — 111 パートナー連絡整理係\n\n| executor | codex |\n| status | running |\n\n## 依頼\n\nメールを整理\n")
            it = one(run)
            self.assertEqual(it["decision"]["mode"], "keep")
            self.assertEqual(it["decision"]["agent"], "codex")
            self.assertIn("現担当のまま", it["decision"]["reason"])
            self.assertTrue(any("逼迫中" in n for n in it["notes"]))
            rt = task_md(t, "# TASK — 715 家族会議週次係\n\n| executor | launchd / gencode |\n| status | queued |\n\n## 依頼\n\n週次で作る\n")
            it = one(rt)
            self.assertEqual(it["decision"]["mode"], "keep")
            self.assertEqual(it["kind"], "operation")

    # 3. ツール固定
    def test_fixed_tool(self):
        with tempfile.TemporaryDirectory() as t:
            it = one(task_md(t, "# TASK — 314 業務品質監査係\n\n| agent_id | 314 |\n| status | queued |\n\n## 依頼\n\n今週のレビュー\n"))
            self.assertEqual(it["decision"]["mode"], "fixed")
            self.assertEqual(it["decision"]["agent"], "claude_code")
            self.assertIn("固定", it["decision"]["reason"])
            res = d.build([task_md(t, "# TASK — 314 業務品質監査係\n\n| agent_id | 314 |\n| status | queued |\n\n## 依頼\n\n今週のレビュー\n")],
                          None, rep(), NOW)
            self.assertIn("✅ でも起動しない", res["text"])
            self.assertNotIn("そのまま貼る依頼文", res["text"])

    # 4. 対外送信の注意
    def test_external_send_note(self):
        it = one({"title": "516 業者への返信の後始末", "text": "業者返信を確認して送信"})
        self.assertTrue(any("対外送信" in n for n in it["notes"]))

    # 5. 運用・整理は実装と区別
    def test_operation_kind(self):
        self.assertEqual(one({"title": "メール整理", "text": "パートナーのメール整理"})["kind"], "operation")
        self.assertEqual(one({"title": "x", "text": "スクリプトを実装"})["kind"], "implement")

    # 6. 手入力の取得日と古い値
    def test_manual_age_and_stale(self):
        txt = d.build([{"title": "x", "text": "実装"}], None, rep(), NOW)["text"]
        self.assertIn("ミスレモン 7%（11/09 手入力）", txt)
        txt = d.build([{"title": "x", "text": "実装"}], None, rep(claude_day="2026-10-20T00:00:00+09:00"), NOW)["text"]
        self.assertIn("古い値", txt)

    def test_design_and_money(self):
        self.assertEqual(one({"title": "作業フローの磨き", "text": "作業フローの磨き"}, rep(claude=1))["decision"]["agent"], "chatgpt_mode")
        it = one({"title": "振込の準備", "text": "振込の準備"}, rep(codex=40, cursor=60, claude=1))
        self.assertEqual(it["decision"]["agent"], "codex")
        self.assertTrue(any("最終承認" in n for n in it["notes"]))

    def test_all_blocked_is_hold(self):
        it = one({"title": "x", "text": "実装"}, rep(codex=95, claude=99, cursor=91, gencode=100))
        self.assertIsNone(it["decision"]["agent"])

    def test_template_and_paste_ready_requests(self):
        with tempfile.TemporaryDirectory() as t:
            tpl = task_md(t, "# TASK — 112 LINE同期監視係\n\n| status | queued |\n\n## 依頼\n\n（何をするか。入力は `input/`）\n\n## 完了条件\n")
            res = d.build([tpl, {"title": "スクリプトを実装", "text": "実装"}], None, rep(), NOW)
            self.assertTrue(res["items"][0]["empty"])
            self.assertIn("そのまま貼る依頼文", res["text"])
            self.assertIn("2. ミスレモンへ:", res["text"])
            self.assertNotIn("1. ミスレモンへ:", res["text"])
            self.assertIn("担当メモ:", res["text"])
            self.assertIn("橋渡し:", res["text"])

    def test_past_records_are_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            task = task_md(t, "# TASK — 999 テスト係\n\n| status | queued |\n\n## 依頼\n\nPlaywright でログインして取得する実装\n\n## 以前の完了タスク\n\n送金\n")
            it = one(task)
            self.assertEqual(it["kind"], "implement")
            self.assertTrue(any("launchd" in n for n in it["notes"]))


if __name__ == "__main__":
    unittest.main()
