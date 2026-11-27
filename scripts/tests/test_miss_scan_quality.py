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


class DedupeTests(unittest.TestCase):
    def test_same_journal_line_on_two_days_is_one(self):
        j = {"source": "obsidian_journal", "snippet": "• 記録を要対応", "hypothesis": "h"}
        out = ms.dedupe_candidates([{**j, "folder": "2026-11-12.md"}, {**j, "folder": "2026-11-13.md"}])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["folder"], "2026-11-12.md・2026-11-13.md")

    def test_partner_folders_stay_separate_and_spacing_is_ignored(self):
        a = {"source": "yoritoori", "folder": "P1", "snippet": "・見積を ご確認ください。"}
        out = ms.dedupe_candidates([a, {**a, "snippet": "見積をご確認ください"}, {**a, "folder": "P2"}])
        self.assertEqual([c["folder"] for c in out], ["P1", "P2"])


if __name__ == "__main__":
    unittest.main()
