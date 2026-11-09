import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_ai_dispatch_suggest as d


def rep(codex=92, claude=7, cursor=51, gencode=100, chatgpt=None):
    return {"period": {"since": "2026-11-03T00:00:00+09:00", "until": "2026-11-10T00:00:00+09:00"},
            "tools": {"codex": {"limits_latest": {"weekly": {"used_pct": codex, "resets_at": "2026-11-12T21:05:51+09:00"}}},
                      "claude_plan": {"pct": claude}, "claude_code": {"limit_hits": [1, 2]},
                      "cursor": {"pct": cursor}, "gencode": {"pct": gencode, "note": "クレジット切れ"},
                      "chatgpt_mode": {"pct": chatgpt}}}


class DispatchTests(unittest.TestCase):
    def test_implement_goes_to_most_room_and_skips_blocked(self):
        r = d.build({"title": "814 点検の実装", "text": "スクリプトを実装"}, None, rep())
        self.assertEqual(r["kind"], "implement")
        self.assertEqual(r["decision"]["agent"], "claude_code")
        ex = "、".join(r["decision"]["excluded"])
        self.assertIn("Codex（92% で逼迫）", ex)
        self.assertIn("フライデー（クレジット切れ）", ex)
        self.assertIn("次: Claude Codeで続行", r["text"])
        self.assertIn("担当メモ:", r["text"])
        self.assertIn("橋渡し:", r["text"])

    def test_design_is_fixed_to_chatgpt(self):
        r = d.build({"title": "作業フローの磨き", "text": "作業フローの磨き"}, None, rep(claude=1))
        self.assertEqual(r["decision"]["agent"], "chatgpt_mode")

    def test_money_only_jarvis_or_codex(self):
        r = d.build({"title": "振込の準備", "text": "振込の準備"}, None, rep(codex=40, cursor=60, claude=1))
        self.assertEqual(r["kind"], "money")
        self.assertEqual(r["decision"]["agent"], "codex")
        self.assertIn("最終承認", r["text"])

    def test_tie_prefers_codex_and_unknown_goes_last(self):
        r = d.build({"title": "x", "text": "実装"}, None, rep(codex=10, claude=10, cursor=None, gencode=None))
        self.assertEqual(r["decision"]["agent"], "codex")

    def test_all_blocked_is_hold(self):
        r = d.build({"title": "x", "text": "実装"}, None, rep(codex=95, claude=99, cursor=91, gencode=100))
        self.assertIsNone(r["decision"]["agent"])
        self.assertIn("次: 人判断のみ", r["text"])

    def test_login_note_and_task_md(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "TASK.md"
            p.write_text("# TASK — 999 テスト係\n\n| task_id | 999-1 |\n\n## 依頼\n\nPlaywright でログインして取得する実装\n\n## 以前の完了タスク\n\n送金\n", encoding="utf-8")
            task = d.read_task(p)
            self.assertEqual(task["task_id"], "999-1")
            r = d.build(task, None, rep())
            self.assertEqual(r["kind"], "implement")  # 過去記録の「送金」は読まない
            self.assertTrue(r["login"])
            self.assertIn("Mac の launchd", r["text"])

    def test_template_task_is_flagged(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "TASK.md"
            p.write_text("# TASK — 112 LINE同期監視係\n\n## 依頼\n\n（何をするか。入力は `input/`）\n\n## 完了条件\n", encoding="utf-8")
            task = d.read_task(p)
            self.assertEqual(task["title"], "112 LINE同期監視係")
            r = d.build(task, None, rep())
            self.assertIn("依頼」が空", r["text"])
            self.assertIn("次: 人判断のみ（渡し票を書いてから）", r["text"])


if __name__ == "__main__":
    unittest.main()
