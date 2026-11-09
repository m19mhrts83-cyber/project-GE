#!/usr/bin/env python3
"""314 判断ログ週次: Loopware 312（task_loop）統合・前週比・共通パターン・改善台帳のテスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_owner_decisions_weekly as wk  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 11, 14, 9, 30, tzinfo=JST)
SINCE = NOW - timedelta(days=7)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


class _Q:
    def __init__(self, data, fail=None):
        self.data, self.fail = data, fail

    def select(self, *_a):
        return self

    def gte(self, col, val):
        self.data = [r for r in self.data if str(r.get(col)) >= val]
        return self

    def order(self, *_a):
        return self

    def range(self, a, b):
        self.data = self.data[a : b + 1]
        return self

    def in_(self, col, vals):
        self.data = [r for r in self.data if str(r.get(col)) in vals]
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError(self.fail)
        return self


class _SB:
    def __init__(self, db, fail=None):
        self.db, self.fail = db, fail or {}

    def table(self, name):
        return _Q(list(self.db.get(name, [])), self.fail.get(name))


def _db():
    topics = [
        {"id": "t-aaaaaaaa1", "topic_text": "青葉の催促", "todoist_task_ids": ["9001"]},
        {"id": "t-bbbbbbbb2", "topic_text": "保険の更新", "todoist_task_ids": []},
        {"id": "t-cccccccc3", "topic_text": "前週の話", "todoist_task_ids": []},
    ]
    decisions = [
        {"id": "d-1", "topic_id": "t-aaaaaaaa1", "choice": "none_of_above", "reason_tags": ["既にある"],
         "updated_at": _iso(1), "decided_via": "app"},
        {"id": "d-2", "topic_id": "t-bbbbbbbb2", "choice": "none_of_above", "reason_tags": ["既にある"],
         "updated_at": _iso(2), "decided_via": "app", "history": [{"choice": "use"}]},
        {"id": "d-3", "topic_id": "t-cccccccc3", "choice": "use", "reason_tags": [],
         "updated_at": _iso(9), "decided_via": "app"},
    ]
    owner = [
        {"id": 11, "decided_at": _iso(1), "surface": "todoist_313", "action": "close", "employee": "313",
         "target_type": "todoist_task", "target_id": "7001", "payload": {"kind": "loopware", "reason_tags": []}},
        {"id": 12, "decided_at": _iso(1), "surface": "todoist_313", "action": "drop", "employee": "313",
         "target_type": "todoist_task", "target_id": "7002",
         "payload": {"kind": "loopware", "reason_tags": ["状況が変わった"]}},
        {"id": 13, "decided_at": _iso(3), "surface": "todoist_312", "action": "dismiss", "employee": "312",
         "target_type": "todoist_task", "target_id": "-", "note": "雑談", "payload": {}},
    ]
    return {"task_loop_decisions": decisions, "task_loop_topics": topics, "owner_decisions": owner}


class LoopwareMergeTests(unittest.TestCase):
    def test_both_tables_are_read_and_split_by_week(self):
        rows, errors = wk.fetch_all_sources(_SB(_db()), SINCE - timedelta(days=7))
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 6)
        cur, prev = wk.split_weeks(rows, since=SINCE)
        self.assertEqual(len(cur), 5)
        self.assertEqual(len(prev), 1)
        emps = {wk.employee_of(r) for r in cur}
        self.assertIn("312L", emps)
        self.assertIn("313L", emps)

    def test_task_loop_row_shape(self):
        rows = wk.fetch_task_loop(_SB(_db()), SINCE)
        r = next(x for x in rows if x["subject"] == "青葉の催促")
        self.assertEqual(r["action"], "none_of_above")
        self.assertEqual(r["reason_tags"], ["既にある"])
        self.assertEqual(r["target_id"], "9001")
        self.assertEqual(wk.verdict_of(r), "見送り")
        self.assertEqual(wk.ref_of(r), "#tl:d-1(todoist 9001)")

    def test_one_table_missing_is_reported_not_fatal(self):
        sb = _SB(_db(), fail={"task_loop_decisions": "PGRST205 no table"})
        rows, errors = wk.fetch_all_sources(sb, SINCE)
        self.assertEqual(len(rows), 3)
        self.assertTrue(errors and errors[0].startswith("task_loop: PGRST205"))
        md = wk.summarize(rows, since=SINCE, until=NOW, read_errors=errors)
        self.assertIn("⚠ 読めなかった: task_loop", md)

    def test_verdicts(self):
        self.assertEqual(wk.verdict_of({"action": "sent", "edited": True}), "修正")
        self.assertEqual(wk.verdict_of({"action": "sent", "edited": False}), "承認")
        self.assertEqual(wk.verdict_of({"action": "drop"}), "修正")
        self.assertEqual(wk.verdict_of({"action": "close"}), "承認")
        self.assertEqual(wk.verdict_of({"action": "xyz"}), "その他")


class SummaryTests(unittest.TestCase):
    def _md(self, ledger=None):
        rows, _ = wk.fetch_all_sources(_SB(_db()), SINCE - timedelta(days=7))
        cur, prev = wk.split_weeks(rows, since=SINCE)
        return wk.summarize(cur, since=SINCE, until=NOW, prev_rows=prev, ledger=ledger or [])

    def test_week_comparison_has_counts_and_denominator(self):
        md = self._md()
        self.assertIn("今週と前週", md)
        # 312 Loopware: 今週 2件とも見送り、前週 1件承認
        self.assertIn("| 312 Todoist起票整理係（Loopware） | 2 | 0/2 0%（前週比 -100pt） | 0/2 0%（前週と同じ） | 2/2 100%（前週比 +100pt） | 1 |", md)
        self.assertIn("読んだ表: ", md)
        self.assertIn("task_loop 2", md)

    def test_common_pattern_needs_two(self):
        md = self._md()
        self.assertIn("| 312 Todoist起票整理係（Loopware） | 既にある | 2 | 見送り 2 |", md)
        self.assertIn("#tl:d-1(todoist 9001)", md)
        # 1件だけのものは候補にしない
        self.assertIn("1件だけの理由", md)
        self.assertNotIn("| 状況が変わった |", md)

    def test_ledger_effect(self):
        text = (
            "# 改善台帳\n\n"
            "| ID | 状態 | 社員 | 指標 | 改善前 | 根拠ID | 分類 | 改善対象 | 想定効果 | PR | 効果 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|\n"
            "| IMP-001 | 実装済 | 312L | 見送り率 | 70% | #tl:d-1 | プロンプト | prompts/proposal.md | 見送り率を下げる | #1 | |\n"
            "| IMP-002 | 提案 | 313L | 修正率 | 50% | #12 | 運用ルール | - | - | | |\n"
        )
        ledger = wk.parse_ledger(text)
        self.assertEqual(len(ledger), 2)
        md = self._md(ledger)
        self.assertIn("| IMP-001 | 312 Todoist起票整理係（Loopware） | 見送り率 | 70% | 100% | 2 |", md)
        self.assertNotIn("| IMP-002 |", md.split("前回までの改善の効果")[1].split("##")[0])

    def test_ledger_template_parses(self):
        p = REPO / "docs/AIエージェントチーム/300_品質・タスク運用管理室/314_業務品質監査係/output/improvements.md"
        self.assertTrue(p.exists())
        for row in wk.parse_ledger(p.read_text(encoding="utf-8")):
            self.assertIn(row.get("指標"), wk.METRICS)


if __name__ == "__main__":
    unittest.main()
