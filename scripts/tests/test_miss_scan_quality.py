#!/usr/bin/env python3
"""312 拾い漏れスキャンの絞り込み（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_todoist_312_miss_scan as ms  # noqa: E402


class AskLineTests(unittest.TestCase):
    def test_clauses_and_plain_statements_are_dropped(self):
        for ln in [
            "　・2年以内の退去：家賃1ヶ月分（通常家賃49,000円）",
            "3. 退去時に全室消臭・清掃を行い、貸主が判断した修繕費用は借主負担とする",
            "緑区の物件で、12月に1室の退去が予定されています。",
        ]:
            self.assertFalse(ms.is_ask_line(ln), ln)

    def test_requests_are_kept(self):
        for ln in [
            "入居者退去の際に保険適用できる特約あれば紹介してください",
            "見積書をご確認いただけますでしょうか。",
            "退去の件、折り返しお願いします",
        ]:
            self.assertTrue(ms.is_ask_line(ln), ln)


class JournalTests(unittest.TestCase):
    def test_front_matter_is_not_used(self):
        text = '---\ndate: "2026-11-12"\nsource: "ChatGPT daily review"\n---\n\n# 2026-11-12\n\n## 生ログ\n\n- 宿題: 見積の返事を出す\n'
        self.assertEqual(ms.journal_signal_line(text), "宿題: 見積の返事を出す")

    def test_none_when_no_signal(self):
        self.assertEqual(ms.journal_signal_line("---\na: b\n---\n普通の日記"), "")


if __name__ == "__main__":
    unittest.main()
