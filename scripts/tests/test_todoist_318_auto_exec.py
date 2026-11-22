#!/usr/bin/env python3
"""318 Todoist消化係 ①自律実行（2-1・2-2）のテスト。ネットワーク・AI API 不要。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "tests"))

import jarvis_todoist_318_triage as tr  # noqa: E402
import jarvis_todoist_318_work as wk  # noqa: E402
from test_todoist_318_phase3 import FakeTodoist, P3Base  # noqa: E402
from test_todoist_318_triage import CRITERIA, NOW, task  # noqa: E402

AI_TASK = "🤖 公開資料の下調べ"


def result(item: dict, status: str = "done", **kw) -> dict:
    r = {
        "task_id": item["task_id"], "work_id": item["work_id"], "snapshot_id": item["snapshot_id"],
        "status": status, "summary": "公開資料を3つ読んで要点をまとめた", "remaining": "",
        "artifacts": [{"name": "調査メモ", "content": "# 要点\n- 1\n- 2"}],
        "actions_taken": ["research", "read", "draft"], "requested_operations": [],
    }
    r.update(kw)
    return r


class AutoBase(P3Base):
    def packet(self):
        return json.loads(self.paths.work_packet.read_text(encoding="utf-8"))["items"]

    def start(self, td, **kw):
        run = self.run_once(td, execute_auto=True, **kw)
        return run, self.packet()

    def later(self, h=1):
        return NOW + timedelta(hours=h)


class DefaultOffTest(AutoBase):
    def test_without_flag_nothing_starts(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        run = self.run_once(td)
        e = run["tasks"][0]
        self.assertEqual(e["category"], "1")
        self.assertNotIn("work", e)
        self.assertFalse(e["planned_action"]["executed"])
        self.assertFalse(self.paths.work.exists())
        self.assertFalse(run["flags"]["execute_auto"])

    def test_work_results_needs_execute_auto_on_cli(self):
        f = self.state / "r.json"
        f.write_text(json.dumps({"results": []}), encoding="utf-8")
        self.assertEqual(tr.main(["--state-dir", str(self.state), "run", "--work-results", str(f)]), 2)


class StartTest(AutoBase):
    def test_start_writes_packet_and_waits(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        run, items = self.start(td, write_comments=True)
        self.assertEqual(run["result"], "success")
        self.assertEqual(run["counts"]["work_started"], 1)
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["task_id"], "a")
        self.assertEqual(it["allowed_actions"], ["research", "read", "draft"])
        self.assertIn("send", it["forbidden"])
        self.assertEqual(self.hist()["a"]["work_318"]["state"], "awaiting_ai")
        e = run["tasks"][0]
        self.assertEqual(e["work"]["state"], "awaiting_ai")
        self.assertNotIn("comment_draft", e)  # 結果待ちの間はコメントしない
        self.assertEqual(td.posts, [])
        self.assertEqual(run["writes"], {"todoist": 0, "slack": 0, "supabase": 0})

    def test_approval_word_moves_to_2_before_start(self):
        td = FakeTodoist([task("a", content="🤖 作業ブランチをマージ")])
        run, items = self.start(td)
        e = run["tasks"][0]
        self.assertEqual(e["category"], "2")
        self.assertEqual(e["moved_from"], "1")
        self.assertIn("マージ", e["reason"])
        self.assertEqual(items, [])
        self.assertEqual(self.hist()["a"]["queue_state"], "pending")
        self.assertEqual(run["counts"]["queued"], 1)  # /313/bulk の待ち（載せるのは --publish の時だけ）

    def test_owner_operation_moves_to_3(self):
        td = FakeTodoist([task("a", content="窓口で書類を受け取り")])
        self.run_once(td, dry=True, emit_packet=True)
        sid = json.loads(self.paths.packet.read_text(encoding="utf-8"))["tasks"][0]["snapshot_id"]
        run, items = self.start(td, ai_answers={"a": {"category": "1", "reason": "調べるだけ", "snapshot_id": sid}})
        self.assertEqual(run["tasks"][0]["category"], "3")
        self.assertEqual(items, [])

    def test_large_goes_weekly_without_start(self):
        td = FakeTodoist([task("a", content="🤖 通知の仕組み化")])
        run, items = self.start(td)
        self.assertEqual(items, [])
        self.assertEqual(run["counts"]["work_weekly"], 1)
        prev = json.loads((self.paths.root / "weekly_handoff.preview.json").read_text(encoding="utf-8"))
        self.assertEqual([(x["id"], x["kind"]) for x in prev["items"]], [("a", "large")])

    def test_stop_switch_means_no_new_start(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        real = tr.stop_switch_on
        calls = {"n": 0}

        def flip(paths, env):
            calls["n"] += 1
            return "" if calls["n"] <= 2 else "停止ファイル STOP"  # 開始チェック（2 回）の後に置かれた

        tr.stop_switch_on = flip
        try:
            run, items = self.start(td)
        finally:
            tr.stop_switch_on = real
        self.assertEqual(items, [])
        self.assertEqual(run["tasks"][0]["work"]["decision"], "hold")
        self.assertEqual(run["counts"]["work_held"], 1)

    def test_missing_scope_does_not_start(self):
        crit = self.state / "crit.yaml"
        crit.write_text(CRITERIA.read_text(encoding="utf-8").split("# ---- ①自律実行の作業範囲")[0], encoding="utf-8")
        td = FakeTodoist([task("a", content=AI_TASK)])
        opts = tr.RunOptions(dry_run=False, sb=self.sb, execute_auto=True)
        run = tr.execute(self.paths, crit, self.env, lambda _t: td, opts, now_fn=lambda: NOW)
        self.assertEqual(run["result"], "partial")
        self.assertFalse(self.paths.work_packet.exists())
        self.assertEqual(run["tasks"][0]["category"], "1")  # 分類はそのまま


class ImportTest(AutoBase):
    def test_done_saves_artifacts_and_comments(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        run = self.run_once(td, now=self.later(), execute_auto=True, work_results=[result(items[0])], write_comments=True)
        self.assertEqual(run["result"], "success")
        self.assertEqual(run["counts"]["work_done"], 1)
        w = self.hist()["a"]["work_318"]
        self.assertEqual(w["state"], "done")
        d = self.paths.work / w["saved_dir"]
        self.assertTrue((d / "01_調査メモ.md").read_text(encoding="utf-8").startswith("# 要点"))
        self.assertEqual(json.loads((d / "progress.json").read_text(encoding="utf-8"))["outcome"], "done")
        self.assertEqual(self.packet(), [])  # 取り込んだ材料は外す
        self.assertEqual(len(td.posts), 1)
        self.assertTrue(td.posts[0][1].startswith("【318】やり切った"))
        self.assertIn("Todoist は閉じていない", td.posts[0][1])
        self.assertTrue(all(p.startswith(("/user", "/tasks", "/comments")) for p in td.paths))  # 読むだけ＋コメント

    def test_partial_records_remaining(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        run = self.run_once(td, now=self.later(), execute_auto=True,
                            work_results=[result(items[0], "partial", remaining="残り2つの資料を読む")], write_comments=True)
        self.assertEqual(run["counts"]["work_partial"], 1)
        self.assertEqual(self.hist()["a"]["work_318"]["remaining"], "残り2つの資料を読む")
        self.assertTrue(td.posts[0][1].startswith("【318】途中"))

    def test_partial_without_remaining_is_rejected(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        run = self.run_once(td, now=self.later(), execute_auto=True, work_results=[result(items[0], "partial")])
        self.assertEqual(run["result"], "partial")
        self.assertFalse((self.paths.work / "a").exists())

    def test_requested_send_moves_to_2_and_waits_for_approval(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        r = result(items[0], "needs_decision", requested_operations=["send"], reason="返事を出すかどうか")
        run = self.run_once(td, now=self.later(), execute_auto=True, work_results=[r], write_comments=True)
        self.assertEqual(run["counts"]["work_to2"], 1)
        h = self.hist()["a"]
        self.assertEqual(h["last_category"], "2")
        self.assertEqual(h["queue_state"], "pending")
        self.assertEqual(h["work_318"]["state"], "approval_wait")
        self.assertFalse((self.paths.work / "a").exists())  # 成果物は取り込まない
        self.assertTrue(td.posts[0][1].startswith("【318】要判断"))
        # 内容が変わって ① に戻っても、本人の回答が来るまで自動で再実行しない
        td.tasks[0]["priority"] = 3
        run3 = self.run_once(td, now=self.later(2), execute_auto=True)
        self.assertEqual(run3["tasks"][0]["work"]["decision"], "hold")
        self.assertEqual(self.packet(), [])

    def test_approval_wait_clears_after_newer_owner_answer(self):
        row = {"work_318": {"state": "approval_wait", "at": "2026-11-23T14:00:00+09:00"}}
        self.assertTrue(tr._approval_waiting(row, None))
        self.assertTrue(tr._approval_waiting(row, {"decided_at": "2026-11-23T04:00:00Z"}))  # 13:00 JST＝前
        self.assertFalse(tr._approval_waiting(row, {"decided_at": "2026-11-23T06:00:00Z"}))  # 15:00 JST＝後
        self.assertFalse(tr._approval_waiting({}, None))

    def test_needs_owner_moves_to_3_and_weekly(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        r = result(items[0], "needs_owner", requested_operations=["owner_login"])
        run = self.run_once(td, now=self.later(), execute_auto=True, work_results=[r])
        self.assertEqual(run["counts"]["work_to3"], 1)
        self.assertEqual(self.hist()["a"]["last_category"], "3")
        self.assertEqual(run["counts"]["handoff"], 1)

    def test_out_of_scope_action_is_not_imported(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        r = result(items[0], actions_taken=["research", "send"])
        run = self.run_once(td, now=self.later(), execute_auto=True, work_results=[r])
        self.assertEqual(run["counts"]["work_to2"], 1)
        self.assertFalse((self.paths.work / "a").exists())

    def test_changed_task_result_is_discarded(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        td.tasks[0]["description"] = "追加の指示"
        run = self.run_once(td, now=self.later(), execute_auto=True, work_results=[result(items[0])])
        outs = run["work"]["results"]
        self.assertEqual(outs[0]["outcome"], "discarded")
        self.assertFalse((self.paths.work / "a").exists())
        # 内容が変わったので新しい材料が出る（古い work_id は使わない）
        self.assertNotEqual(self.packet()[0]["work_id"], items[0]["work_id"])

    def test_wrong_snapshot_or_unknown_work_is_discarded(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        bad = [result(items[0], snapshot_id="x"), {**result(items[0]), "work_id": "w-unknown"}]
        run = self.run_once(td, now=self.later(), execute_auto=True, work_results=bad)
        self.assertEqual([o["outcome"] for o in run["work"]["results"]], ["discarded", "discarded"])

    def test_stale_packet_is_not_imported(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        run = self.run_once(td, now=NOW + timedelta(days=4), execute_auto=True, work_results=[result(items[0])])
        self.assertEqual(run["work"]["results"][0]["outcome"], "discarded")

    def test_stop_switch_before_import_keeps_material(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        real = tr.stop_switch_on
        calls = {"n": 0}

        def flip(paths, env):
            calls["n"] += 1
            return "" if calls["n"] <= 2 else "停止ファイル STOP"

        tr.stop_switch_on = flip
        try:
            run = self.run_once(td, now=self.later(), execute_auto=True, work_results=[result(items[0])])
        finally:
            tr.stop_switch_on = real
        self.assertIn("中断点", run["work"]["stopped"])
        self.assertEqual(run["counts"]["work_done"], 0)
        self.assertEqual(len(self.packet()), 1)  # 残りは材料に残る

    def test_unreadable_current_state_is_not_imported(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        _, items = self.start(td)
        td.fail_reads["a"] = td.reads.get("a", 0) + 1
        run = self.run_once(td, now=self.later(), execute_auto=True, work_results=[result(items[0])])
        self.assertIn(run["work"]["results"][0]["outcome"], ("unverified",))
        self.assertEqual(len(self.packet()), 1)


class DryRunTest(AutoBase):
    def test_dry_run_plans_but_makes_no_artifacts(self):
        td = FakeTodoist([task("a", content=AI_TASK)])
        run, items = self.start(td, dry=True)
        self.assertEqual(len(items), 1)  # 材料（やる予定）は出る
        self.assertFalse(self.paths.history.exists())
        run2 = self.run_once(td, dry=True, now=self.later(), execute_auto=True, work_results=[result(items[0])])
        self.assertEqual(run2["work"]["results"][0]["outcome"], "done")
        self.assertFalse((self.paths.work / "a").exists())  # 成果物は作らない
        self.assertEqual(len(self.packet()), 1)  # dry-run では材料から外さない


class WeeklyLargeTest(unittest.TestCase):
    def test_large_handoff_reason_in_weekly_pick(self):
        from datetime import date, datetime, timezone  # noqa: PLC0415

        import jarvis_todoist_318_handoff as ho  # noqa: PLC0415
        import jarvis_todoist_weekly_pick as wp  # noqa: PLC0415

        jst = timezone(timedelta(hours=9))
        now = datetime(2026, 11, 15, 17, 0, tzinfo=jst)
        tasks = [{"id": "1", "content": "🤖 通知の仕組み化", "labels": [], "priority": 1, "added_at": "2026-11-01T00:00:00Z"}]
        doc = {"published": True, "generated_at": now.isoformat(),
               "items": [{"id": "1", "reason": ho.HANDOFF_LARGE_TEXT, "kind": "large"}]}
        snap = wp.build_snapshot(tasks=tasks, completed_last_week=[], pick_history={}, inlet_topics=[],
                                 today=date(2026, 11, 15), now=now, handoff=ho.handoff_map(doc, now))
        self.assertEqual(snap["candidates"][0]["reasons"][0]["tag"], "handoff_318_large")


class WorkUnitTest(unittest.TestCase):
    def test_safe_names(self):
        self.assertEqual(wk.safe_name("../../etc/passwd", 1), "01_etc_passwd.md")
        self.assertEqual(wk.safe_name("", 2), "02_artifact.md")
        with self.assertRaises(ValueError):
            wk.safe_tid("../..")
        self.assertEqual(wk.safe_tid("6abc_X-1"), "6abc_X-1")

    def test_scope_rejects_code_change(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.yaml"
            txt = CRITERIA.read_text(encoding="utf-8").replace(
                'allowed_actions: ["research", "read", "draft"]', 'allowed_actions: ["research", "code_change"]')
            p.write_text(txt, encoding="utf-8")
            with self.assertRaises(wk.ScopeError):
                wk.load_scope(p)
        self.assertEqual(wk.load_scope(CRITERIA)["allowed_actions"], ["research", "read", "draft"])

    def test_precheck_order(self):
        sc = wk.load_scope(CRITERIA)
        kw = dict(scope=sc, large=False, owner_op_hit=False, approval_wait=False, stop_reason="")
        self.assertEqual(wk.precheck("資料を読む", **kw)[0], "start")
        self.assertEqual(wk.precheck("資料を読む", **{**kw, "stop_reason": "時間上限"})[0], "hold")
        self.assertEqual(wk.precheck("本番へデプロイ", **kw)[0], "to2")
        self.assertEqual(wk.precheck("資料を読む", **{**kw, "owner_op_hit": True})[0], "to3")
        self.assertEqual(wk.precheck("資料を読む", **{**kw, "large": True})[0], "weekly")
        self.assertEqual(wk.precheck("本番へデプロイ", **{**kw, "approval_wait": True})[0], "hold")


if __name__ == "__main__":
    unittest.main()
