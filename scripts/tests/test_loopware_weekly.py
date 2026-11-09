#!/usr/bin/env python3
"""ループウェア週次分析（機械で束ねる部分）とルール帳への反映のテスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_learned_rules as lr  # noqa: E402
import jarvis_loopware_apply_rules as ap  # noqa: E402
import jarvis_loopware_weekly as lw  # noqa: E402


def row(i, surface="triage", action="skipped", **kw):
    r = {"id": i, "surface": surface, "action": action, "target_type": "triage_item", "target_id": f"t{i}", "payload": {}}
    r.update(kw)
    return r


class HypothesesTests(unittest.TestCase):
    def test_hide_candidate_from_repeated_skips(self):
        rows = [
            row(1, from_email="News <info@news.example.com>", payload={"reason_tags": ["promo"]}),
            row(2, from_email="info@news.example.com", payload={"reason_tags": ["no_reply"]}),
            row(3, from_email="boss@x.jp", action="sent"),
            row(4, from_email="boss@x.jp"),
        ]
        c = lw.hypotheses(rows)
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["kind"], "hide")
        self.assertEqual(c[0]["rule_line"], "hide | from:info@news.example.com | scope=partner")
        self.assertEqual(c[0]["status"], "hypothesis")  # 少ないログ
        self.assertEqual(c[0]["evidence"], [1, 2])

    def test_hesitated_is_not_ng(self):
        rows = [row(1, action="hesitated", from_email="a@x.jp"), row(2, action="hesitated", from_email="a@x.jp")]
        self.assertEqual(lw.hypotheses(rows), [])

    def test_keep_rewrite_template_and_limit(self):
        rows = [
            row(1, surface="triage_miss", action="wrong", payload={"from_email": "ok@x.jp"}),
            row(2, action="sent", edited=True, partner="LEAF"),
            row(3, action="sent", edited=True, partner="LEAF"),
            row(4, action="next_wrong", payload={"next_step_id": "default_todo"}),
            row(5, action="next_wrong", payload={"next_step_id": "default_todo"}),
            *[row(10 + i, from_email=f"n{i}@spam.jp") for i in range(0)],
        ]
        kinds = [c["kind"] for c in lw.hypotheses(rows)]
        self.assertEqual(len(kinds), 3)
        self.assertEqual(set(kinds), {"keep", "rewrite", "template"})
        rw = next(c for c in lw.hypotheses(rows) if c["kind"] == "rewrite")
        self.assertTrue(rw["needs_ai"])
        self.assertEqual(rw["employee"], "211")

    def test_rejected_and_stable_id(self):
        rows = [row(1, from_email="a@x.jp"), row(2, from_email="a@x.jp")]
        cid = lw.hypotheses(rows)[0]["id"]
        self.assertEqual(cid, lw.cand_id("hide", "a@x.jp"))
        self.assertEqual(lw.hypotheses(rows, rejected={cid}), [])

    def test_sections_and_notes(self):
        rows = [
            row(1, action="sent", payload={"applied_rules": ["R116-002"], "outcome": "take"}),
            row(2, action="hesitated", payload={"stay_reason": "no_time"}),
            row(3, action="next_good", payload={"next_step_id": "wait_snooze3"}),
            row(4, surface="rule_review", action="rule_accept", payload={"rule_id": "R116-003", "employee": "116", "text": "宣伝は出さない"}),
        ]
        md = lw.sections(rows, [])
        self.assertIn("R116-002: 採った 1", md)
        self.assertIn("時間がない 1", md)
        self.assertIn("wait_snooze3: 良い 1／1", md)
        self.assertIn("採用: 宣伝は出さない", md)
        note = lw.obsidian_note(rows, [], week="2026-W45")
        self.assertIn("# 判断ログ 2026-W45", note)
        imp = lw.improvement_lines(rows, week="2026-W45")
        self.assertIn("116", imp)
        self.assertTrue(any("R116-003" in x for x in imp["116"]))
        self.assertTrue(any("R116-002" in x for x in imp["116"]))


class OwnerCommentTests(unittest.TestCase):
    def test_comment_is_listed_for_314(self):
        rows = [
            {"id": 1, "surface": "rule_review", "action": "comment", "target_id": "C1234abcd",
             "note": "請求書だけ見送り", "payload": {"candidate_id": "C1234abcd", "text": "a@x.jp を出さない"}},
            {"id": 2, "surface": "rule_review", "action": "rule_once", "target_id": "C1234abcd", "payload": {}},
        ]
        md = lw.sections(rows, [])
        self.assertIn("あなたのひとこと", md)
        self.assertIn("[C1234abcd] a@x.jp を出さない → 「請求書だけ見送り」", md)
        self.assertNotIn("あなたのひとこと", lw.sections(rows[1:], []))


class ApplyTests(unittest.TestCase):
    BOOK = (REPO / "docs/AIエージェントチーム/100_連絡・物件動向把握室/116_メール要対応係/learned_rules.md").read_text(encoding="utf-8")

    def test_add_then_remove(self):
        t1, rid = ap.add_rule(self.BOOK, employee="116", rule_line="hide | from:a@x.jp | scope=partner",
                              today="2026-11-08", evidence=[1, 2], note="宣伝 | 通知")
        self.assertEqual(rid, "R116-001")
        self.assertNotIn(ap.PLACEHOLDER, t1)
        book = lr.parse_rulebook(t1)
        self.assertEqual(book.warnings, [])
        self.assertEqual([r.id for r in book.confirmed], ["R116-001"])
        self.assertEqual(book.confirmed[0].evidence, ["1", "2"])
        t2, rid2 = ap.add_rule(t1, employee="116", rule_line="demote-10 | subject:請求書", today="2026-11-08", evidence=[], note="")
        self.assertEqual(rid2, "R116-002")
        self.assertEqual([r.id for r in lr.parse_rulebook(t2).confirmed], ["R116-001", "R116-002"])
        # 仮説・例外の節は残る
        self.assertIn("## 仮説", t2)
        t3, hit = ap.remove_rule(t2, "R116-001")
        self.assertTrue(hit)
        self.assertEqual([r.id for r in lr.parse_rulebook(t3).confirmed], ["R116-002"])


if __name__ == "__main__":
    unittest.main()
