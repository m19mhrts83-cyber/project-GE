#!/usr/bin/env python3
"""今週の9件（jarvis_todoist_weekly_pick）の純粋部分のテスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jarvis_todoist_weekly_pick as w  # noqa: E402

JST = timezone(timedelta(hours=9))
SUN = date(2026, 11, 15)


def task(i, content, **kw):
    return {"id": str(i), "content": content, "labels": kw.pop("labels", []), "priority": kw.pop("priority", 1),
            "added_at": kw.pop("added_at", "2026-11-01T00:00:00Z"), **kw}


class DatesTests(unittest.TestCase):
    def test_target_monday(self):
        self.assertEqual(w.target_monday(SUN), date(2026, 11, 16))
        self.assertEqual(w.target_monday(date(2026, 11, 16)), date(2026, 11, 16))
        self.assertEqual(w.target_monday(date(2026, 11, 10)), date(2026, 11, 16))

    def test_pick_dates_mon_wed_fri(self):
        self.assertEqual(w.pick_dates(date(2026, 11, 16)), ["2026-11-16", "2026-11-18", "2026-11-20"])


class OwnerTests(unittest.TestCase):
    def test_owner_classification(self):
        self.assertTrue(w.is_owner_task(task(1, "ローン残高を登録")))
        self.assertTrue(w.is_owner_task(task(2, "🦾依頼 運動会をまとめる")))
        self.assertFalse(w.is_owner_task(task(3, "🤖 [自律化] 仕様を決める")))
        self.assertTrue(w.is_owner_task(task(4, "🤖 [要ボス] PR #261 を決める")))
        self.assertTrue(w.is_owner_task(task(5, "🤖 [メール要対応][白井] 富士見台")))
        self.assertFalse(w.is_owner_task(task(6, "🤖 [要フォロー][card] 引落")))
        self.assertFalse(w.is_owner_task(task(7, "子", parent_id="1")))

    def test_weekend_agent_slot(self):
        sat = {"date": "2026-11-14"}
        self.assertFalse(w.is_owner_task(task(8, "【提案】[自律化] 58_ 承認案の実装", due=sat)))
        self.assertTrue(w.is_owner_task(task(9, "【提案】[自律化] 58_ 承認案の実装", due={"date": "2026-11-16"})))
        self.assertTrue(w.is_owner_task(task(10, "運動会の結果をNotionへ", due=sat)))

    def test_hard(self):
        self.assertTrue(w.is_hard(task(1, "振込", deadline={"date": "2026-11-21"})))
        self.assertTrue(w.is_hard(task(2, "名中説明会 参加証印刷", due={"date": "2026-11-14"})))
        self.assertFalse(w.is_hard(task(3, "ローン残高を登録", due={"date": "2026-11-18"})))


class ReasonTests(unittest.TestCase):
    def test_deadline_and_partner(self):
        score, rs = w.reasons_for(task(1, "🤖 防蟻工事費の振込", deadline={"date": "2026-11-21"}, priority=3), today=SUN, weeks_carried=0)
        tags = [r["tag"] for r in rs]
        self.assertEqual(tags[0], "deadline")
        self.assertIn("partner_money", tags)
        self.assertIn("あと6日", rs[0]["text"])
        self.assertGreater(score, 50)

    def test_carried_ranks(self):
        s0, _ = w.reasons_for(task(1, "資料を作る"), today=SUN, weeks_carried=0)
        s2, rs = w.reasons_for(task(1, "資料を作る"), today=SUN, weeks_carried=2)
        self.assertGreater(s2, s0)
        self.assertEqual(rs[0]["tag"], "carried")


class SnapshotTests(unittest.TestCase):
    def test_build_and_recommend(self):
        tasks = [task(i, f"仕事{i}", priority=2) for i in range(1, 15)]
        tasks.append(task(100, "🤖 【番頭指摘】防蟻工事費の振込（ボス実施）", deadline={"date": "2026-11-17"}))
        tasks.append(task(101, "🤖 [自律化] AIだけ"))
        tasks.append(task(102, "前の週の残り", due={"date": "2026-11-12"}))
        snap = w.build_snapshot(tasks=tasks, completed_last_week=[{"content": "済"}], pick_history={"102": 1},
                                inlet_topics=[{"id": "t1", "topic_text": "物件の件を整理したい", "created_at": "2026-11-11T00:00:00Z"}],
                                today=SUN, now=datetime(2026, 11, 15, 17, tzinfo=JST))
        self.assertEqual(snap["week"], "2026-11-16")
        self.assertEqual(len(snap["recommended"]), 9)
        ids = [r["id"] for r in snap["recommended"]]
        self.assertNotIn("101", ids)
        self.assertIn("100", ids)
        # 締切 11/17 の振込は月曜に置く
        self.assertEqual(next(r["day"] for r in snap["recommended"] if r["id"] == "100"), "2026-11-16")
        self.assertIn("102", ids)
        self.assertEqual(snap["last"]["left"], 1)
        self.assertEqual(snap["last"]["done"], 1)
        self.assertEqual(snap["inlet"][0]["waited_days"], 4)
        self.assertEqual(len(snap["next_preview"]), 7)  # 16件中 9件を置いた残り
        for d in snap["days"]:
            self.assertLessEqual(sum(1 for r in snap["recommended"] if r["day"] == d), 3)


class PlanTests(unittest.TestCase):
    def test_plan_ops(self):
        ops = w.plan_ops({
            "set_due": [{"id": "1", "date": "2026-11-16"}, {"id": "2", "date": "bad"}],
            "clear_due": ["3"],
            "notes": [{"id": "4", "text": "やめる（313で片付け）"}],
            "inlet": [{"topic_id": "t1", "title": "物件の整理", "date": "2026-11-18"}],
            "inlet_skip": ["t2"],
        })
        kinds = [k for k, _ in ops]
        self.assertEqual(kinds, ["set_due", "clear_due", "comment", "inlet", "inlet_skip"])


if __name__ == "__main__":
    unittest.main()
