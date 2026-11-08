#!/usr/bin/env python3
"""ルール帳（learned_rules.md）を読む処理と、候補への効かせ方のテスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_learned_rules as lr  # noqa: E402
import jarvis_mail_action_slack_post as ma  # noqa: E402
import jarvis_night_triage as nt  # noqa: E402

BOOK = """# ルール帳 — 116

説明文の中の `- R116-999 | hide | * |` は読まない。

## 確定ルール

- R116-001 | hide | from:@news.example.com | scope=partner | v1 2026-11-08 | 根拠 12,15 | 宣伝メール
- R116-002 | boost+30 | partner:ミニテック & lane:partner | v1 2026-11-08 | 修繕の連絡は上に
- R116-003 | demote | subject:請求書 | v2 2026-11-09
- R116-004 | rewrite | partner:LEAF | v1 | 冒頭は「いつもお世話になっております。」
- R116-005 | explode | * |
- R116-002 | hide | * | 重複

## 仮説

- R116-010 | hide | domain:example.org | 効かせない

## 例外

- R116-020 | hide | from:boss@news.example.com | 例外は keep として効く

## 参照例

- R116-030 | hide | * | 読むだけ
"""


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.book = lr.parse_rulebook(BOOK)

    def test_sections_and_warnings(self):
        ids = {r.id: r.status for r in self.book.rules}
        self.assertEqual(ids["R116-001"], "confirmed")
        self.assertEqual(ids["R116-010"], "hypothesis")
        self.assertEqual(ids["R116-020"], "exception")
        self.assertNotIn("R116-030", ids)
        self.assertNotIn("R116-999", ids)
        self.assertNotIn("R116-005", ids)
        self.assertTrue(any("効き目" in w for w in self.book.warnings))
        self.assertTrue(any("重複" in w for w in self.book.warnings))

    def test_fields(self):
        r = next(r for r in self.book.rules if r.id == "R116-001")
        self.assertEqual(r.scope, "partner")
        self.assertEqual(r.version, "v1 2026-11-08")
        self.assertEqual(r.evidence, ["12", "15"])
        self.assertEqual(next(r for r in self.book.rules if r.id == "R116-002").step, 30)
        self.assertEqual(next(r for r in self.book.rules if r.id == "R116-003").step, 20)
        self.assertEqual(next(r for r in self.book.rules if r.id == "R116-020").effect, "keep")

    def test_max_confirmed(self):
        lines = "\n".join(f"- R1-{i:03d} | demote | subject:x{i}" for i in range(12))
        book = lr.parse_rulebook("## 確定ルール\n" + lines)
        self.assertEqual(len(book.confirmed), 10)
        self.assertTrue(any("上限" in w for w in book.warnings))


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.book = lr.parse_rulebook(BOOK)

    def test_hide_and_exception(self):
        a = lr.apply_to_row(self.book, {"from_email": "News <info@news.example.com>"})
        self.assertTrue(a.hidden)
        self.assertEqual(a.rule_ids, ["R116-001"])
        b = lr.apply_to_row(self.book, {"from_email": "boss@news.example.com", "subject": "請求書"})
        self.assertFalse(b.hidden)
        self.assertEqual(b.delta, 0)
        self.assertEqual(b.rule_ids, ["R116-020"])

    def test_boost_demote_and_hypothesis_not_applied(self):
        a = lr.apply_to_row(self.book, {"partner": "ミニテック", "lane": "partner", "subject": "請求書の件"})
        self.assertEqual(a.delta, 10)
        self.assertEqual(a.rule_ids, ["R116-002", "R116-003"])
        c = lr.apply_to_row(self.book, {"from_email": "a@example.org"})
        self.assertFalse(c.hidden)
        self.assertEqual(c.rule_ids, [])

    def test_rewrite_lines(self):
        self.assertEqual(lr.rewrite_lines(self.book, {"partner": "LEAF"}),
                         [("R116-004", "冒頭は「いつもお世話になっております。」")])
        self.assertEqual(lr.rewrite_lines(self.book, {"partner": "X"}), [])

    def test_missing_book_is_empty(self):
        self.assertEqual(lr.load_rulebook("no-such").rules, [])


class ConsumerTests(unittest.TestCase):
    def test_rank_uses_rule_delta(self):
        rows = [
            {"id": "a", "subject": "A", "received_at": "2026-11-01T00:00:00+09:00", "gmail_message_id": "1"},
            {"id": "b", "subject": "B", "received_at": "2026-11-01T00:00:00+09:00", "gmail_message_id": "2",
             "_rule_delta": 30, "_applied_rules": ["R116-002"]},
        ]
        out = ma.rank_candidates(rows, limit=5)
        self.assertEqual(out[0]["id"], "b")
        self.assertIn("rules:+30", out[0]["_score_reasons"])

    def test_posted_payload_carries_rules(self):
        pl = ma._stamp_posted_payload({"applied_rules": ["old"]}, score=1, summary="", slack_channel=None,
                                      slack_ts=None, digest_channel=None, digest_ts=None, applied_rules=["R116-002"])
        self.assertEqual(pl["applied_rules"], ["R116-002"])
        pl2 = ma._stamp_posted_payload(pl, score=1, summary="", slack_channel=None, slack_ts=None,
                                       digest_channel=None, digest_ts=None)
        self.assertNotIn("applied_rules", pl2)

    def test_draft_prompt_includes_rules(self):
        c = {"partner_name": "LEAF", "subject": "s", "context": []}
        p = nt.build_draft_prompt(c, {"summary": ""}, [("R211-001", "冒頭は短く")])
        self.assertIn("- 冒頭は短く", p)
        self.assertNotIn("R211-001", p)
        self.assertNotIn("冒頭は短く", nt.build_draft_prompt(c, {"summary": ""}))


class RealBooksTests(unittest.TestCase):
    def test_repo_rulebooks_parse_cleanly(self):
        for emp in lr.EMPLOYEE_DIRS:
            book = lr.load_rulebook(emp)
            self.assertEqual(book.warnings, [], f"{emp}: {book.warnings}")


if __name__ == "__main__":
    unittest.main()
