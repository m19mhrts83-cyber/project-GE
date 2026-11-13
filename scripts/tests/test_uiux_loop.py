#!/usr/bin/env python3
"""UI/UX の好みループ（scripts/jarvis_uiux_loop.py）のテスト（ネットワーク不要）。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_uiux_loop as u  # noqa: E402
import jarvis_loopware_weekly as lw  # noqa: E402


def fix(i, work, trip, action, applied=None, tags=None, app="dashboard"):
    return {"id": i, "surface": "uiux_fix", "action": action, "target_id": work, "decided_at": f"2026-11-14T0{i}:00:00Z",
            "payload": {"work_id": work, "round_trip": trip, "app": app, "applied_rules": applied or [], "reason_tags": tags or []}}


class FixRowTests(unittest.TestCase):
    def test_row_shape(self):
        r = u.fix_row(app="dashboard", work="pr395-home", trip=2, verdict="wrong", what="長押しで並べ替えたい",
                      item="efficiency", tags=["steps"], applied=["R800-001"], pr=395, idem_key="k-1")
        self.assertEqual(r["surface"], "uiux_fix")
        self.assertEqual(r["action"], "wrong")
        self.assertEqual(r["source"], "script")
        self.assertEqual(r["employee"], "814")
        self.assertEqual(r["payload"]["round_trip"], 2)
        self.assertEqual(r["payload"]["concept"], "手数の少なさ")
        self.assertEqual(r["payload"]["outcome"], "ng")
        self.assertEqual(r["payload"]["idem_key"], "k-1")

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            u.fix_row(app="x", work="w", trip=1, verdict="good", what="")
        with self.assertRaises(ValueError):
            u.fix_row(app="dashboard", work="w", trip=1, verdict="good", what="", tags=["nope"])
        with self.assertRaises(ValueError):
            u.fix_row(app="dashboard", work="w", trip=1, verdict="good", what="", item="nope")


class MetricsTests(unittest.TestCase):
    def test_first_ok_and_trips(self):
        rows = [
            fix(1, "a", 1, "good", applied=["R800-001"]),
            fix(2, "b", 1, "comment"),
            fix(3, "b", 1, "wrong", tags=["phone"]),
            fix(4, "b", 2, "wrong", tags=["phone", "layout"]),
            fix(5, "b", 3, "good"),
        ]
        m = u.fix_metrics(rows)
        self.assertEqual(m["works"], 2)
        self.assertEqual(m["first_ok"], 1)
        self.assertEqual(m["avg_trips"], 2.0)
        self.assertEqual(m["with_rules"], {"works": 1, "first_ok_rate": 1.0})
        self.assertEqual(m["without_rules"], {"works": 1, "first_ok_rate": 0.0})
        self.assertEqual(m["wrong_tags"], {"phone": 2, "layout": 1})
        self.assertIn("1案目OK 1／2 件（50%）", u.metrics_lines(m)[0])

    def test_weekly_section(self):
        out = lw.sections([fix(1, "a", 1, "good")], [])
        self.assertIn("画面の好み", out)
        self.assertNotIn("画面の好み", lw.sections([], []))


class BookTests(unittest.TestCase):
    def test_adopted_and_book_lines(self):
        rows = [
            {"id": 10, "action": "rule_accept", "target_id": "r:P1", "decided_at": "2026-11-14T01:00:00Z", "payload": {"text": "動きで見せる", "concept": "見た目の美しさと統一感"}},
            {"id": 11, "action": "rule_accept", "target_id": "r:P2", "decided_at": "2026-11-14T02:00:00Z", "payload": {"text": "B", "app": "kurashift"}},
            {"id": 12, "action": "rule_revert", "target_id": "r:P2", "decided_at": "2026-11-14T03:00:00Z", "payload": {}},
        ]
        lines = u.book_lines(u.adopted_rules(rows))
        self.assertEqual(lines, ["- R800-001 | ui | app:* & item:見た目の美しさと統一感 | v1 2026-11-14 | 根拠 10 | 動きで見せる"])
        md = u.BOOK.read_text(encoding="utf-8")
        new = u.replace_section(md, "確定ルール", lines, "（なし）")
        self.assertEqual(u.book_section(new, "確定ルール"), lines)
        self.assertEqual(u.book_section(new, "仮説"), u.book_section(md, "仮説"))

    def test_seed_round_is_valid(self):
        seed = json.loads((REPO / "docs" / "uiux_loop" / "round_seed_20261114.json").read_text(encoding="utf-8"))
        self.assertEqual(u.validate_round(seed), [])
        self.assertEqual(u.validate_round({"id": "x", "title": "t", "stage": "plan", "plans": [{"id": "A", "label": "a"}]}),
                         ["stage=plan なら plans を2つ以上（1案で済む小さな直しは put せず log-fix だけ）"])


if __name__ == "__main__":
    unittest.main()
