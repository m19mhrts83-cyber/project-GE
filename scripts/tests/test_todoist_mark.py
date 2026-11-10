#!/usr/bin/env python3
"""Todoist 件名の印（🤖／🦾依頼／印なし）のテスト。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_todoist_mark as m  # noqa: E402


class Mark(unittest.TestCase):
    def test_ai_and_requested(self):
        self.assertEqual(m.mark_title("[要フォロー][x] 要約"), "🤖 [要フォロー][x] 要約")
        self.assertEqual(m.mark_title("件名", requested=True), "🦾依頼 件名")

    def test_no_double_mark(self):
        self.assertEqual(m.mark_title("🤖 件名"), "🤖 件名")
        self.assertEqual(m.mark_title("🦾依頼 件名"), "🦾依頼 件名")

    def test_strip(self):
        self.assertEqual(m.strip_mark("🤖 件名"), "件名")
        self.assertEqual(m.strip_mark("🦾依頼 件名"), "件名")
        self.assertEqual(m.strip_mark("件名"), "件名")

    def test_keep_mark_on_rewrite(self):
        self.assertEqual(m.keep_mark("新しい件名", "🦾依頼 古い件名"), "🦾依頼 新しい件名")
        self.assertEqual(m.keep_mark("新しい件名", "古い件名"), "🤖 新しい件名")


class Duplicate(unittest.TestCase):
    def test_marked_and_unmarked_are_same_task(self):
        try:
            import jarvis_todoist_api as api  # noqa: E402
        except ImportError as e:  # 依存が無い環境では飛ばす
            self.skipTest(str(e))
        tasks = [{"id": "1", "content": "🤖 [メール要対応][A] 件名", "due": None}]
        self.assertEqual(api.find_open_duplicate(tasks, "[メール要対応][A] 件名", None)["id"], "1")
        self.assertEqual(api.find_open_duplicate(tasks, "🤖 [メール要対応][A] 件名", None)["id"], "1")


class WatchTitle(unittest.TestCase):
    def test_watch_title_is_marked(self):
        try:
            import jarvis_watch_todoist_sync as w  # noqa: E402
        except ImportError as e:
            self.skipTest(str(e))
        self.assertTrue(w._title_for({"id": "vpoint", "summary": "残高"}).startswith("🤖 [要フォロー][vpoint]"))


if __name__ == "__main__":
    unittest.main()
