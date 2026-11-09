#!/usr/bin/env python3
"""下書きの判断ログ（draft_review）のテスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_draft_decision_log as dl  # noqa: E402
import jarvis_learned_rules as lr  # noqa: E402
import jarvis_loopware_weekly as lw  # noqa: E402


def make(**kw):
    base = dict(case="c1", recipient="今村さん", channel="chatwork", before="あ\nい\n", after="あ\nう\n",
                from_label="v1", to_label="v2", change_types=["言い回し"], reason="短く", rule_hint=None, final=False)
    base.update(kw)
    return dl.build_row(**base)


class BuildRowTests(unittest.TestCase):
    def test_revise_row_shape(self):
        r = make()
        self.assertEqual(r["surface"], "draft_review")
        self.assertEqual(r["action"], "revise")
        self.assertEqual(r["partner"], "今村さん")
        self.assertTrue(r["edited"])
        self.assertEqual(r["payload"]["idem_key"], "draft:c1:v1->v2:revise")
        self.assertEqual(r["payload"]["lines_added"], 1)
        self.assertFalse(r["payload"]["reason_missing"])
        self.assertEqual(r["employee"], "211")

    def test_final_is_sent_and_missing_reason_is_flagged(self):
        r = make(final=True, reason=None)
        self.assertEqual(r["action"], "sent")
        self.assertTrue(r["payload"]["reason_missing"])
        self.assertNotIn("reason", r["payload"])

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            make(channel="fax")
        with self.assertRaises(ValueError):
            make(change_types=["謎"])
        with self.assertRaises(ValueError):
            make(after="あ\nい\n")

    def test_sql_is_idempotent(self):
        sql = dl.to_sql(make())
        self.assertIn("where not exists", sql)
        self.assertIn("draft:c1:v1->v2:revise", sql)


class LoopTests(unittest.TestCase):
    def test_two_revisions_to_same_recipient_make_rewrite_candidate(self):
        rows = [dict(make(case="a"), id=1), dict(make(case="b", rule_hint="数字を根拠に"), id=2)]
        cands = lw.hypotheses(rows)
        rw = [c for c in cands if c["kind"] == "rewrite"]
        self.assertEqual(len(rw), 1)
        self.assertEqual(rw[0]["employee"], "211")
        self.assertEqual(rw[0]["rule_line"], "rewrite | partner:今村さん")
        self.assertIn("数字を根拠に", rw[0]["why"])

    def test_context_lists_confirmed_rules_for_recipient(self):
        book = lr.parse_rulebook(
            "## 確定ルール\n- R211-001 | rewrite | partner:今村さん | v1 2026-11-09 | 根拠 1 | 検証済みの数字を添える\n"
            "- R211-002 | rewrite | partner:LEAF | v1 2026-11-09 | 根拠 2 | 別の相手\n"
        )
        text = dl.context_text("今村さん", recent=[{"decided_at": "2026-11-07T00:00", "payload": {"case": "c1", "version_from": "v1", "version_to": "v2", "change_types": ["方針"], "rule_hint": "h"}}], book=book)
        self.assertIn("R211-001", text)
        self.assertNotIn("R211-002", text)
        self.assertIn("理由未確認", text)


class PushPullTests(unittest.TestCase):
    def test_push_row_and_sql(self):
        row = dl.draft_review_row(case="c", recipient="今村さん", channel="chatwork", text="本文", context="ルール")
        self.assertEqual(row["versions"][0]["label"], "v1")
        self.assertEqual(row["versions"][0]["by"], "agent")
        self.assertIn("insert into public.draft_reviews", dl.draft_review_sql(row))
        with self.assertRaises(ValueError):
            dl.draft_review_row(case="c", recipient="x", channel="fax", text="a", context=None)

    def test_pull_skips_reverted_and_lists_comments(self):
        row = {"case_name": "c", "recipient": "今村さん", "status": "done", "versions": [
            {"label": "v1", "text": "a"},
            {"label": "v2", "text": "b", "comments": [{"quote": "a", "text": "直して"}]},
            {"label": "v3", "text": "z", "reverted": True},
        ]}
        out = dl.pull_text(row)
        self.assertIn("いまの版 v2", out)
        self.assertIn("\nb\n", out)
        self.assertIn("「a」: 直して", out)


if __name__ == "__main__":
    unittest.main()
