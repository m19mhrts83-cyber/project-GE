#!/usr/bin/env python3
"""318 Todoist消化係 Phase 1 のテスト（ネットワーク・Slack・Todoist 不要。ダミーデータ）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_todoist_313_judgment as jd313  # noqa: E402
import jarvis_todoist_318_triage as tr  # noqa: E402

CRITERIA = REPO / "config" / "todoist_318_criteria.yaml"
NOW = datetime(2026, 11, 23, 14, 0, tzinfo=tr.JST)  # 313 の枠（10:15–11:30）の外
TODAY = NOW.date()
UID = "u1"


def task(i: str, days_over: int = 3, content: str = "ダミー作業", **kw) -> dict:
    t = {
        "id": i,
        "content": content,
        "description": "",
        "due": {"date": (TODAY - timedelta(days=days_over)).isoformat()},
        "labels": [],
        "priority": 1,
        "responsible_uid": None,
    }
    t.update(kw)
    return t


class FakeReader:
    """GET だけを受ける偽物。呼ばれたパスを全部覚える。"""

    def __init__(self, tasks, comments=None, fail_comments=(), fail_tasks=False, user=None):
        self.tasks = tasks
        self.comments = comments or {}
        self.fail_comments = set(fail_comments)
        self.fail_tasks = fail_tasks
        self.user = {"id": UID} if user is None else user
        self.paths: list[str] = []

    def get(self, path: str):
        self.paths.append(path)
        if path == "/user":
            return self.user
        if path.startswith("/tasks"):
            if self.fail_tasks:
                raise urllib.error.HTTPError(path, 500, "x", {}, None)
            return {"results": self.tasks, "next_cursor": None}
        if path.startswith("/comments"):
            tid = path.split("task_id=")[1].split("&")[0]
            if tid in self.fail_comments:
                raise urllib.error.HTTPError(path, 503, "x", {}, None)
            return {"results": self.comments.get(tid, []), "next_cursor": None}
        raise AssertionError(f"想定外のパス {path}")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.paths = tr.Paths(self.state)
        (self.state / "todoist_313_judgments.json").write_text(json.dumps({"keep": {}, "streak": {}}), encoding="utf-8")
        self.env = {"TODOIST_API_TOKEN_OWNER": "dummy"}

    def tearDown(self):
        self.tmp.cleanup()

    def run_once(self, reader, dry=False, env=None, **kw):
        opts = tr.RunOptions(dry_run=dry, **kw)
        return tr.execute(self.paths, CRITERIA, env or self.env, lambda _tok: reader, opts, now_fn=lambda: NOW)


class PreflightTest(Base):
    def test_stop_switch_stops_without_reading(self):
        self.paths.root.mkdir(parents=True)
        self.paths.stop.write_text("", encoding="utf-8")
        r = FakeReader([task("a")])
        run = self.run_once(r)
        self.assertEqual(run["result"], "stopped")
        self.assertEqual(r.paths, [])
        self.assertFalse(self.paths.lock.exists())
        self.assertTrue(run["saved"])

    def test_lock_busy_fails_and_keeps_other_lock(self):
        self.paths.root.mkdir(parents=True)
        self.paths.lock.write_text(json.dumps({"run_id": "other", "pid": 1}), encoding="utf-8")
        run = self.run_once(FakeReader([task("a")]))
        self.assertEqual(run["result"], "failed")
        self.assertEqual(run["stop_code"], "lock_busy")
        self.assertTrue(self.paths.lock.exists())  # 他人のロックは外さない

    def test_lock_released_after_success(self):
        run = self.run_once(FakeReader([]))
        self.assertEqual(run["result"], "success")
        self.assertFalse(self.paths.lock.exists())

    def test_no_owner_token(self):
        run = self.run_once(FakeReader([]), env={"TODOIST_API_TOKEN": "x"})
        self.assertEqual(run["stop_code"], "no_owner_token")
        self.assertEqual(run["result"], "failed")

    def test_permission_error(self):
        class R(FakeReader):
            def get(self, path):
                raise urllib.error.HTTPError(path, 401, "x", {}, None)

        run = self.run_once(R([]))
        self.assertEqual(run["stop_code"], "permission")

    def test_313_window_and_lock(self):
        at = NOW.replace(hour=10, minute=40)
        opts = tr.RunOptions(dry_run=True)
        run = tr.execute(self.paths, CRITERIA, self.env, lambda _t: FakeReader([]), opts, now_fn=lambda: at)
        self.assertEqual(run["stop_code"], "overlap_313_window")
        (self.state / "agent_run_locks.json").write_text(
            json.dumps({"locks": {"todoist:x": {"agent_id": "313", "status": "running"}}}), encoding="utf-8"
        )
        run = self.run_once(FakeReader([]))
        self.assertEqual(run["stop_code"], "overlap_313")


class BasisTest(Base):
    def test_missing_313_judgments_is_safe_stop(self):
        (self.state / "todoist_313_judgments.json").unlink()
        run = self.run_once(FakeReader([task("a")]))
        self.assertEqual(run["result"], "failed")
        self.assertEqual(run["stop_code"], "basis_missing")

    def test_broken_history_is_safe_stop(self):
        self.paths.root.mkdir(parents=True)
        self.paths.history.write_text("{broken", encoding="utf-8")
        run = self.run_once(FakeReader([task("a")]))
        self.assertEqual(run["stop_code"], "basis_unreadable")

    def test_history_missing_after_live_run_is_safe_stop(self):
        self.run_once(FakeReader([task("a")]))
        self.paths.history.unlink()
        run = self.run_once(FakeReader([task("a")]))
        self.assertEqual(run["stop_code"], "basis_missing")

    def test_criteria_only_adopted_gives_category1(self):
        rules, _ = tr.load_criteria(CRITERIA)
        for r in rules:
            if r.category == "1":
                self.assertEqual(r.status, "adopted")
                self.assertTrue(r.decision_id)

    def test_bad_criteria(self):
        bad = self.state / "bad.yaml"
        bad.write_text("rules: [{id: X, status: adopted, category: '1', match: {title_any: [a]}}]", encoding="utf-8")
        with self.assertRaises(tr.SafeStop):
            tr.load_criteria(bad)


class ExtractTest(Base):
    def test_read_failure_is_not_zero(self):
        run = self.run_once(FakeReader([], fail_tasks=True))
        self.assertEqual(run["result"], "failed")
        self.assertEqual(run["stop_code"], "read_failed")

    def test_truncated_pagination_fails(self):
        class R(FakeReader):
            def get(self, path):
                if path.startswith("/tasks"):
                    return {"results": [task("a")], "next_cursor": "more"}
                return super().get(path)

        run = self.run_once(R([]))
        self.assertEqual(run["stop_code"], "read_truncated")

    def test_substring_does_not_make_important(self):
        # 313 の IMPORTANT_RE は「高」の部分一致で「高い棚」のような語にも加点していた
        a = task("a", content="高い棚を片付ける", days_over=3)
        b = task("b", content="【緊急】ほか", days_over=3)
        c = task("c", content="ほか", days_over=3, labels=["要ボス"])
        self.assertFalse(tr.is_important(a))
        self.assertTrue(tr.is_important(b))
        self.assertTrue(tr.is_important(c))
        # URL の中の語でも拾わない
        self.assertFalse(tr.is_hard({"id": "e", "content": "見る https://x.example/支払", "due": {"date": TODAY.isoformat()}}))

    def test_deadline_first_then_today_then_overdue(self):
        old = task("old", days_over=50, priority=4)
        today_t = task("today", days_over=0)
        dl = task("dl", days_over=1, deadline={"date": (TODAY + timedelta(days=2)).isoformat()})
        order = [t["id"] for t in tr.rank([old, today_t, dl], TODAY, {})]
        self.assertEqual(order, ["dl", "today", "old"])

    def test_ties_rotate_by_last_examined(self):
        # 313 は min(超過,60) で同点になり、毎日同じ古い順の5件に集中した
        ts = [task(f"t{i}", days_over=60 + i) for i in range(8)]
        hist = {f"t{i}": {"last_examined": "2026-11-22"} for i in range(7, 2, -1)}
        top = [t["id"] for t in tr.rank(ts, TODAY, hist)[:3]]
        self.assertEqual(top, ["t2", "t1", "t0"])  # 見ていない方を先に

    def test_filters_assignee_and_future(self):
        ts = [
            task("mine", responsible_uid=UID),
            task("other", responsible_uid="u2"),
            task("future", days_over=-3),
            task("nodue", due=None),
        ]
        got = [t["id"] for t in tr.candidate_filter(ts, UID, TODAY)]
        self.assertEqual(got, ["mine"])

    def test_max_five_and_carry_over(self):
        ts = [task(f"t{i}", days_over=i + 1) for i in range(9)]
        run = self.run_once(FakeReader(ts))
        self.assertEqual(run["counts"]["processed"], 5)
        self.assertEqual(run["counts"]["carried_over"], 4)
        self.assertEqual(run["result"], "success")


class ChangeTest(Base):
    def test_second_run_skips_unchanged_and_reclassifies_changed(self):
        ts = [task("a"), task("b"), task("c")]
        comments = {"b": []}
        self.run_once(FakeReader(ts, comments))
        # b にだけ人のコメントが付いた。c は自分（【318】）のコメントだけ → 変化に数えない
        comments2 = {
            "a": [{"id": "c3", "content": "【AIチーム】見たよ（受けた）\n引用: …", "posted_at": "2026-11-23T01:00:00Z"}],
            "b": [{"id": "c1", "content": "こうして", "posted_at": "2026-11-23T01:00:00Z"}],
            "c": [{"id": "c2", "content": "【318】記録", "posted_at": "2026-11-23T01:00:00Z"}],
        }
        run = self.run_once(FakeReader(ts, comments2))
        st = {e["task_id"]: e for e in run["tasks"]}
        self.assertEqual(st["a"]["status"], "unchanged")
        self.assertEqual(st["c"]["status"], "unchanged")
        self.assertEqual(st["b"]["status"], "changed")
        self.assertEqual(st["b"]["changed_fields"], ["comments"])
        self.assertEqual(run["counts"]["skipped_unchanged"], 2)
        self.assertEqual(run["counts"]["processed"], 1)

    def test_same_note_count_skips_comment_read(self):
        self.run_once(FakeReader([task("a", note_count=1)], {"a": [{"id": "c1", "content": "x"}]}))
        r = FakeReader([task("a", note_count=1)], {"a": [{"id": "c1", "content": "x"}]})
        run = self.run_once(r)
        self.assertEqual(run["tasks"][0]["status"], "unchanged")
        self.assertEqual(run["tasks"][0]["comments_checked"], "count_only")
        self.assertFalse(any(p.startswith("/comments") for p in r.paths))

    def test_ack_raises_count_but_stays_unchanged(self):
        self.run_once(FakeReader([task("a", note_count=1)], {"a": [{"id": "c1", "content": "x"}]}))
        ack = {"id": "c2", "content": "【AIチーム】見たよ（受けた）"}
        run = self.run_once(FakeReader([task("a", note_count=2)], {"a": [{"id": "c1", "content": "x"}, ack]}))
        self.assertEqual(run["tasks"][0]["status"], "unchanged")
        self.assertEqual(run["tasks"][0]["comments_checked"], "read")
        # 3回目は新しい数（2）で手がかりが更新されているので読まない
        r = FakeReader([task("a", note_count=2)], {"a": [{"id": "c1", "content": "x"}, ack]})
        self.run_once(r)
        self.assertFalse(any(p.startswith("/comments") for p in r.paths))

    def test_due_priority_dependency_changes_detected(self):
        self.run_once(FakeReader([task("a")]))
        a2 = task("a", days_over=1, priority=3)
        child = task("k", parent_id="a", due=None)
        run = self.run_once(FakeReader([a2, child]))
        e = next(x for x in run["tasks"] if x["task_id"] == "a")
        self.assertEqual(set(e["changed_fields"]), {"due", "priority", "dependency"})

    def test_kept_in_313_is_skipped(self):
        t = task("a")
        j = {"keep": {}, "streak": {}}
        jd313.record_keep(j, "a", jd313.fingerprint(t))
        (self.state / "todoist_313_judgments.json").write_text(json.dumps(j), encoding="utf-8")
        run = self.run_once(FakeReader([t]))
        self.assertEqual(run["tasks"][0]["status"], "skip_kept_313")
        self.assertEqual(run["counts"]["skipped_kept_313"], 1)

    def test_comment_read_failure_is_hold_and_partial(self):
        run = self.run_once(FakeReader([task("a"), task("b")], fail_comments={"a"}))
        st = {e["task_id"]: e for e in run["tasks"]}
        self.assertEqual(st["a"]["status"], "hold")
        self.assertEqual(run["result"], "partial")
        self.assertNotIn("a", json.loads(self.paths.history.read_text())["tasks"])

    def test_dry_run_does_not_write_history(self):
        run = self.run_once(FakeReader([task("a")]), dry=True)
        self.assertEqual(run["result"], "success")
        self.assertFalse(self.paths.history.exists())
        self.assertTrue((self.paths.runs / f"{run['run_id']}.json").exists())


class ClassifyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules, _ = tr.load_criteria(CRITERIA)

    def cat(self, **kw):
        return tr.classify(task("x", **kw), self.rules)

    def test_unsure_is_2(self):
        c = self.cat(content="何かやる")
        self.assertEqual(c["category"], "2")
        self.assertEqual(c["rule_ids"], [])

    def test_ai_mark_is_1_with_adopted_decision(self):
        c = self.cat(content="🤖 監視の結果を確かめる")
        self.assertEqual(c["category"], "1")
        self.assertIn("D-20261110-todoist-mark", c["applied_decision_ids"])

    def test_ai_mark_with_owner_words_is_2(self):
        self.assertEqual(self.cat(content="🤖 どうするか決める")["category"], "2")
        self.assertEqual(self.cat(content="🦾依頼 先方へ返信")["category"], "2")
        self.assertEqual(self.cat(content="🤖 [要ボス] 確認")["category"], "2")

    def test_owner_operation_is_3_only_via_proposed_hint(self):
        c = self.cat(content="🤖 窓口で受け取り")
        self.assertEqual(c["category"], "3")
        self.assertEqual(c["applied_decision_ids"], [])  # 提案は採用済み基準として記録しない
        self.assertTrue(c["hint_rule_ids"])

    def test_large_flag(self):
        c = self.cat(content="🤖 通知の仕組みを実装")
        self.assertTrue(c["large"])

    def test_ai_answer_rules(self):
        base = self.cat(content="何かやる")
        up = tr.apply_ai_answer(base, {"category": "1", "reason": "調べるだけ", "snapshot_id": "s"}, "s")
        self.assertEqual(up["category"], "1")
        self.assertEqual(up["classified_by"], "ai(claude_code)")
        blocked = self.cat(content="先方へ返信")
        kept = tr.apply_ai_answer(blocked, {"category": "1", "reason": "x", "snapshot_id": "s"}, "s")
        self.assertEqual(kept["category"], "2")
        stale = tr.apply_ai_answer(base, {"category": "1", "reason": "x", "snapshot_id": "old"}, "s")
        self.assertEqual(stale["category"], "2")


class SafetyTest(Base):
    def test_only_get_paths_and_no_writes(self):
        r = FakeReader([task("a"), task("b", content="🤖 x")])
        run = self.run_once(r)
        self.assertEqual(run["writes"], {"todoist": 0, "slack": 0})
        self.assertTrue(all(p == "/user" or p.startswith(("/tasks", "/comments")) for p in r.paths))
        self.assertFalse(hasattr(tr.TodoistReader, "post"))

    def test_log_has_required_fields_and_no_titles(self):
        run = self.run_once(FakeReader([task("a", content="秘密の題名")]))
        raw = (self.paths.runs / f"{run['run_id']}.json").read_text(encoding="utf-8")
        hist = self.paths.history.read_text(encoding="utf-8")
        self.assertNotIn("秘密の題名", raw)
        self.assertNotIn("秘密の題名", hist)
        e = run["tasks"][0]
        for k in ("task_id", "reason", "applied_decision_ids", "proposal", "next_recheck", "processed_at", "category"):
            self.assertIn(k, e)
        self.assertIn("adopted_decision_ids", run["basis"])
        self.assertIn("報告案", run["report_draft"])

    def test_save_failure_is_not_success(self):
        self.paths.root.mkdir(parents=True)
        self.paths.runs.write_text("ファイルなのでディレクトリを作れない", encoding="utf-8")
        run = self.run_once(FakeReader([task("a")]), dry=True)
        self.assertFalse(run["saved"])
        self.assertEqual(run["result"], "failed")

    def test_time_limit_carries_over(self):
        ticks = iter([0.0] + [0.0] + [61 * 60.0] * 10)
        opts = tr.RunOptions(dry_run=True)
        run = tr.execute(
            self.paths, CRITERIA, self.env, lambda _t: FakeReader([task("a"), task("b")]), opts,
            now_fn=lambda: NOW, clock=lambda: next(ticks),
        )
        self.assertEqual(run["result"], "success")
        self.assertIn("時間上限", run["stop_reason"])
        self.assertEqual(run["counts"]["carried_over"], 1)


if __name__ == "__main__":
    unittest.main()
