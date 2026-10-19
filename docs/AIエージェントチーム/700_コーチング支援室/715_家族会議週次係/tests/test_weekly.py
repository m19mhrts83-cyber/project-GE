#!/usr/bin/env python3
"""715 家族会議週次係 — ネットワーク不要のスモークテスト。

  cd ~/git-repos && ~/selenium_env/venv/bin/python \
    docs/AIエージェントチーム/700_コーチング支援室/715_家族会議週次係/tests/test_weekly.py
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "scripts"))

import friday_family_meeting_weekly as f  # noqa: E402
import friday_notion_ops as n  # noqa: E402


class TestDates(unittest.TestCase):
    def test_latest_sunday_from_monday(self) -> None:
        self.assertEqual(f.latest_sunday(date(2026, 10, 19)), date(2026, 10, 18))

    def test_latest_sunday_from_sunday(self) -> None:
        self.assertEqual(f.latest_sunday(date(2026, 10, 25)), date(2026, 10, 25))

    def test_parse_date(self) -> None:
        self.assertEqual(f.parse_date("2026/10/18"), date(2026, 10, 18))
        self.assertEqual(f.parse_date("20261018"), date(2026, 10, 18))


class TestCorrection(unittest.TestCase):
    def test_aliases(self) -> None:
        out, used = f.correct_text("さあちゃんとまーくん", {"さあちゃん": "さわ", "まーくん": "たまき"})
        self.assertEqual(out, "さわとたまき")
        self.assertEqual(len(used), 2)

    def test_no_op(self) -> None:
        out, used = f.correct_text("そのまま", {"さあ": "さわ"})
        self.assertEqual(out, "そのまま")
        self.assertEqual(used, [])


class TestBlocks(unittest.TestCase):
    def test_md_to_blocks(self) -> None:
        blocks = n.md_to_blocks("## 見出し\n- 箇条書き\n1. 番号\n\n段落")
        types = [b["type"] for b in blocks]
        self.assertEqual(types, ["heading_3", "bulleted_list_item", "numbered_list_item", "paragraph"])

    def test_bold(self) -> None:
        rt = n.rich_text("**太字**と通常")
        self.assertTrue(any((it.get("annotations") or {}).get("bold") for it in rt))

    def test_dated_title(self) -> None:
        m = n.DATED_TITLE_RE.match("(2026/10/18) 家族会議")
        self.assertIsNotNone(m)
        self.assertEqual(m.groups(), ("2026", "10", "18"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
