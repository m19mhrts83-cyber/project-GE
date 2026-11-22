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


class WeightTests(unittest.TestCase):
    """判断の重さ（A すぐ決まる／B じっくり）。基準は本物の config を読む。"""

    @classmethod
    def setUpClass(cls):
        cls.cfg = w.load_weight()

    def test_config_loads(self):
        self.assertEqual(self.cfg["deep_per_week"], 1)
        self.assertTrue(self.cfg["decision_id"])
        self.assertEqual(self.cfg["labels"]["quick"], "すぐ決まる")
        self.assertEqual(self.cfg["labels"]["deep"], "じっくり")

    def test_deep_words(self):
        wt, why = w.classify_weight(task(1, "サービスの方針を検討する"), self.cfg)
        self.assertEqual(wt, "deep")
        self.assertIn("検討", why)

    def test_deep_by_subtasks_and_rally(self):
        self.assertEqual(w.classify_weight(task(1, "資料をまとめる"), self.cfg, children=2)[0], "deep")
        wt, why = w.classify_weight(task(1, "資料をまとめる", note_count=6), self.cfg, weeks_carried=2)
        self.assertEqual(wt, "deep")
        self.assertIn("6件", why)

    def test_quick(self):
        self.assertEqual(w.classify_weight(task(1, "PR を承認する"), self.cfg)[0], "quick")
        self.assertEqual(w.classify_weight(task(1, "どれにする", description="A案: 今週／B案: 来週"), self.cfg)[0], "quick")
        self.assertEqual(w.classify_weight(task(1, "電話する"), self.cfg, handoff_kind="owner")[0], "quick")
        self.assertEqual(w.classify_weight(task(1, "片付け", labels=["quick"]), self.cfg)[0], "quick")

    def test_large_handoff_is_deep(self):
        self.assertEqual(w.classify_weight(task(1, "作業"), self.cfg, handoff_kind="large")[0], "deep")

    def test_unknown(self):
        self.assertEqual(w.classify_weight(task(1, "ローン残高を登録"), self.cfg), ("unknown", "手がかりなし"))
        wt, why = w.classify_weight(task(1, "方針を承認する"), self.cfg)  # 2 対 2
        self.assertEqual(wt, "unknown")
        self.assertIn("割れている", why)
        wt, why = w.classify_weight(task(1, "資料", note_count=5), self.cfg)  # B 1点だけ（2点に届かない）
        self.assertEqual(wt, "unknown")
        self.assertIn("弱い", why)

    def test_unreadable_config_is_unknown_not_quick(self):
        with self.assertRaises(w.WeightConfigError):
            w.load_weight(Path("/nonexistent/todoist_weekly_weight.yaml"))
        wt, why = w.classify_weight(task(1, "PR を承認する"), None, error="x.yaml が無い")
        self.assertEqual(wt, "unknown")
        self.assertIn("基準が読めない", why)

    def _snap(self, tasks, cfg="default"):
        return w.build_snapshot(tasks=tasks, completed_last_week=[], pick_history={}, inlet_topics=[], today=SUN,
                                now=datetime(2026, 11, 15, 17, tzinfo=JST), weight_cfg=self.cfg if cfg == "default" else cfg)

    def test_one_deep_per_week_and_quick_front(self):
        tasks = [task(i, f"方針を検討{i}", priority=4) for i in range(1, 4)]  # B×3（点が高い）
        tasks += [task(10 + i, f"PR を承認{i}", priority=2) for i in range(1, 7)]  # A×6
        tasks += [task(20 + i, f"仕事{i}") for i in range(1, 6)]  # 未判別
        snap = self._snap(tasks)
        rec = {r["id"]: r["day"] for r in snap["recommended"]}
        # 9件の上限はじっくり枠（火・金の2回）を含めて数える → 月水金は7件
        self.assertEqual(len(rec), 7)
        frame = snap["deep_frame"]
        self.assertEqual(frame["days"], ["2026-11-17", "2026-11-20"])  # 火・金
        self.assertEqual(frame["recommended"], "1")
        self.assertEqual(frame["staff_steps"], ["チャッピー相談", "図で確認", "本人判断", "運用で確認"])
        self.assertFalse(any(i in rec for i in ("1", "2", "3")))
        self.assertEqual([x["id"] for x in snap["weight"]["deferred"]], ["2", "3"])
        self.assertIn("翌週以降", snap["weight"]["deferred"][0]["reason"])
        self.assertEqual(snap["next_preview"][:2], ["2", "3"])
        self.assertEqual(snap["weight"]["recommended"], {"quick": 6, "deep": 1, "unknown": 1})
        # A は月→水→金の順に前倒し（月・水が A で埋まる）
        mon, wed, fri = snap["days"]
        quick_days = [rec[str(10 + i)] for i in range(1, 7)]
        self.assertEqual(quick_days.count(mon), 3)
        self.assertEqual(quick_days.count(wed), 3)
        self.assertEqual(list(rec.values()).count(fri), 1)
        for d in snap["days"]:
            self.assertLessEqual(sum(1 for v in rec.values() if v == d), 3)

    def test_second_deep_with_deadline_this_week_stays(self):
        tasks = [task(1, "方針を検討A", priority=4, labels=["properties"]), task(2, "方針を検討B", deadline={"date": "2026-11-22"})]
        snap = self._snap(tasks)
        self.assertEqual([c["id"] for c in snap["candidates"]], ["1", "2"])  # 締切のある B が2件目
        self.assertEqual(snap["deep_frame"]["recommended"], "1")
        self.assertEqual({r["id"] for r in snap["recommended"]}, {"2"})  # 枠の外でも月水金に置く
        self.assertEqual(snap["weight"]["deferred"], [])

    def test_frame_without_deep_candidate_is_empty_but_reserved(self):
        tasks = [task(i, f"仕事{i}") for i in range(1, 15)]
        snap = self._snap(tasks)
        self.assertIsNone(snap["deep_frame"]["recommended"])
        self.assertEqual(len(snap["recommended"]), 7)  # 枠は本人が社員のフロー磨き込み等を入れる用に空けておく

    def test_staff_for_the_week_fills_frame(self):
        cfg = {**self.cfg, "deep_frame": {**self.cfg["deep_frame"],
                                          "staff_by_week": {"2026-11-16": {"staff": "社員X", "decision_id": "D-test"}}}}
        tasks = [task(1, "方針を検討A", priority=4)] + [task(i, f"仕事{i}") for i in range(10, 20)]
        snap = self._snap(tasks, cfg=cfg)
        f = snap["deep_frame"]
        self.assertIsNone(f["recommended"])
        self.assertEqual(f["staff"]["staff"], "社員X")
        self.assertEqual(f["staff"]["decision_id"], "D-test")
        self.assertIn("作業フローの磨き込み", f["staff"]["title"])
        self.assertEqual([x["id"] for x in snap["weight"]["deferred"]], ["1"])
        self.assertIn("社員X", snap["weight"]["deferred"][0]["reason"])
        self.assertEqual(len(snap["recommended"]), 7)

    def test_config_staff_this_week(self):
        st = self.cfg["deep_frame"]["staff_by_week"].get("2026-11-23")
        self.assertTrue(st and st["staff"].startswith("317") and st["decision_id"])

    def test_staff_frame_does_not_create_todoist_task(self):
        self.assertEqual(w.plan_ops({"deep_new": [{"title": "x", "date": "2026-11-17"}]}), [])

    def test_no_config_keeps_old_behavior(self):
        tasks = [task(i, f"方針を検討{i}", priority=4) for i in range(1, 4)]
        snap = self._snap(tasks, cfg=None)
        self.assertEqual(len(snap["recommended"]), 3)
        self.assertFalse(snap["weight"]["ok"])
        self.assertEqual(snap["weight"]["candidates"]["unknown"], 3)


class SaturdayTests(unittest.TestCase):
    """土曜 07:00 の snapshot（2026-11-23〜）でも、対象は次の月曜からの週。"""

    def test_saturday_targets_next_monday(self):
        sat = date(2026, 11, 28)
        self.assertEqual(w.target_monday(sat), date(2026, 11, 30))
        self.assertEqual(w.pick_dates(w.target_monday(sat)), ["2026-11-30", "2026-12-02", "2026-12-04"])

    def test_saturday_snapshot_week_and_left(self):
        tasks = [
            task(1, "この週の水曜に置いた", due={"date": "2026-11-25"}),
            task(2, "土曜の今日に置いた", due={"date": "2026-11-28"}),
            task(3, "次の週の火曜に置いた", due={"date": "2026-12-01"}),
            task(4, "締切が来週", deadline={"date": "2026-12-03"}),
        ]
        snap = w.build_snapshot(tasks=tasks, completed_last_week=[], pick_history={}, inlet_topics=[],
                                today=date(2026, 11, 28), now=datetime(2026, 11, 28, 7, tzinfo=JST))
        self.assertEqual(snap["week"], "2026-11-30")
        self.assertEqual(snap["last"]["week"], "2026-11-23")  # 「結果・残り」は作った週（月曜から）
        self.assertEqual(snap["last"]["left"], 2)  # 月曜より前の期日（水・土）
        self.assertEqual({x["id"] for x in snap["dated_in_week"]}, {"3"})
        c4 = next(c for c in snap["candidates"] if c["id"] == "4")
        self.assertIn("あと5日", c4["reasons"][0]["text"])  # 土曜から数える
        self.assertEqual(w._md(snap["week"]), "11/30")


if __name__ == "__main__":
    unittest.main()
