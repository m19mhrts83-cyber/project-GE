#!/usr/bin/env python3
"""318 Todoist消化係 Phase 3 準備のテスト（【318】コメント・朝枠の排他・① のやる予定・launchd 雛形）。ネットワーク不要。"""
from __future__ import annotations

import re
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "tests"))

import jarvis_comment_dispatch as cd  # noqa: E402
import jarvis_todoist_318_comment as cm  # noqa: E402
import jarvis_todoist_318_triage as tr  # noqa: E402
import jarvis_todoist_morning_slot as ms  # noqa: E402
import jarvis_todoist_webhook_handle as wh  # noqa: E402
from test_todoist_318_triage import CRITERIA, NOW, UID, FakeSb, task  # noqa: E402

AT_1030 = NOW.replace(hour=10, minute=30)


class FakeTodoist:
    """読む口（GET）とコメントの追記口（POST /comments）の偽物。投稿はコメント一覧に入る。"""

    def __init__(self, tasks, comments=None):
        self.tasks = tasks
        self.comments: dict[str, list[dict]] = comments or {}
        self.mode = "ok"  # ok／timeout_posted／timeout_lost／http400／http503／noid
        self.fail_reads: dict[str, int] = {}  # task_id -> この回数目以降のコメント読取を失敗させる
        self.reads: dict[str, int] = {}
        self.posts: list[tuple[str, str]] = []
        self.paths: list[str] = []
        self._n = 0

    # reader
    def get(self, path: str):
        self.paths.append(path)
        if path == "/user":
            return {"id": UID}
        if path.startswith("/tasks"):
            return {"results": self.tasks, "next_cursor": None}
        if path.startswith("/comments"):
            tid = path.split("task_id=")[1].split("&")[0]
            self.reads[tid] = self.reads.get(tid, 0) + 1
            if tid in self.fail_reads and self.reads[tid] >= self.fail_reads[tid]:
                raise urllib.error.HTTPError(path, 503, "x", {}, None)
            return {"results": list(self.comments.get(tid, [])), "next_cursor": None}
        raise AssertionError(f"想定外のパス {path}")

    # writer
    def post_comment(self, task_id: str, content: str):
        self.posts.append((task_id, content))
        self._n += 1
        row = {"id": f"c{self._n}", "content": content, "posted_at": f"2026-11-23T0{self._n % 10}:00:00Z"}
        if self.mode == "timeout_posted":
            self.comments.setdefault(task_id, []).append(row)
            raise TimeoutError("read timed out")
        if self.mode == "timeout_lost":
            raise TimeoutError("read timed out")
        if self.mode == "http400":
            raise urllib.error.HTTPError("/comments", 400, "bad", {}, None)
        if self.mode == "http503":
            raise urllib.error.HTTPError("/comments", 503, "x", {}, None)
        self.comments.setdefault(task_id, []).append(row)
        if self.mode == "noid":
            return {}
        return row


class P3Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.paths = tr.Paths(self.state)
        (self.state / "todoist_313_judgments.json").write_text(json.dumps({"keep": {}}), encoding="utf-8")
        self.env = {"TODOIST_API_TOKEN_OWNER": "dummy"}
        self.sb = FakeSb()
        self.t313 = self.state / "t313_pending.json"
        p = mock.patch.object(tr.ms, "T313_PENDING", self.t313)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_once(self, td: FakeTodoist, *, now=NOW, dry=False, **kw):
        kw.setdefault("sb", self.sb)
        kw.setdefault("poster", lambda ch, text: True)
        kw.setdefault("writer_factory", lambda _tok: td)
        opts = tr.RunOptions(dry_run=dry, **kw)
        return tr.execute(self.paths, CRITERIA, self.env, lambda _t: td, opts, now_fn=lambda: now)

    def hist(self):
        return json.loads(self.paths.history.read_text(encoding="utf-8"))["tasks"]

    def c318(self, tid):
        return self.hist()[tid].get("comment_318") or {}


class CommentOffByDefaultTest(P3Base):
    def test_default_writes_nothing_but_keeps_drafts(self):
        td = FakeTodoist([task("a"), task("b", content="送信する")])
        run = self.run_once(td)
        self.assertEqual(run["result"], "success")
        self.assertEqual(td.posts, [])
        self.assertEqual(run["writes"]["todoist"], 0)
        self.assertNotIn("comments", run)
        drafts = [e["comment_draft"] for e in run["tasks"] if e.get("category")]
        self.assertEqual(len(drafts), 2)
        for d in drafts:
            self.assertTrue(d.startswith("【318】"))
            self.assertIn(f"処理ID: {run['run_id']}", d)

    def test_dry_run_never_writes(self):
        td = FakeTodoist([task("a")])
        run = self.run_once(td, dry=True, write_comments=True)
        self.assertEqual(td.posts, [])
        self.assertFalse(run["comments"]["enabled"])

    def test_no_comment_when_log_not_saved(self):
        td = FakeTodoist([task("a")])
        real = tr.atomic_write_json

        def boom(path, data):
            if "runs" in str(path):
                raise OSError("disk")
            return real(path, data)

        with mock.patch.object(tr, "atomic_write_json", side_effect=boom):
            run = self.run_once(td, write_comments=True)
        self.assertEqual(run["result"], "failed")
        self.assertEqual(td.posts, [])
        self.assertFalse(run["comments"]["enabled"])


class CommentWriteTest(P3Base):
    def test_posts_only_changed_and_never_twice(self):
        td = FakeTodoist([task("a"), task("b", content="送信する")])
        run1 = self.run_once(td, write_comments=True)
        self.assertEqual(run1["result"], "success")
        self.assertEqual(len(td.posts), 2)
        self.assertEqual(run1["writes"]["todoist"], 2)
        for tid, body in td.posts:
            # a は②③の印なしで①（62_聞く基準の既定）、b は「送信」で②
            self.assertTrue(body.startswith("【318】要判断" if tid == "b" else "【318】"), body[:20])
            if tid == "a":
                self.assertFalse(body.startswith("【318】要判断"))
            self.assertTrue(cm.has_run_id(body, run1["run_id"]))
        self.assertEqual(self.c318("a")["state"], "posted")
        self.assertNotIn("body", self.c318("a"))
        # 2 回目: 自分の【318】コメントは変化に数えない → 変化なし → 書かない
        run2 = self.run_once(td, now=NOW + timedelta(hours=1), write_comments=True)
        self.assertEqual(run2["counts"]["skipped_unchanged"], 2)
        self.assertEqual(len(td.posts), 2)
        self.assertEqual(run2["writes"]["todoist"], 0)

    def test_same_content_is_not_written_again(self):
        td = FakeTodoist([task("a")])
        self.run_once(td, write_comments=True)
        td.tasks[0]["priority"] = 2  # 変化はあるが、分類・コメントの中身は同じ
        run = self.run_once(td, now=NOW + timedelta(hours=1), write_comments=True)
        self.assertEqual(run["counts"]["processed"], 1)
        self.assertEqual(run["comments"]["same_as_last"], 1)
        self.assertEqual(len(td.posts), 1)

    def test_different_content_is_written(self):
        td = FakeTodoist([task("a")])
        self.run_once(td, write_comments=True)
        td.tasks[0]["content"] = "役所の窓口で提出"  # ② → ③
        run = self.run_once(td, now=NOW + timedelta(hours=1), write_comments=True)
        self.assertEqual(len(td.posts), 2)
        self.assertTrue(td.posts[1][1].startswith("【318】本人作業"))
        self.assertEqual(run["comments"]["posted"], 1)

    def test_precheck_finds_same_content_already_in_todoist(self):
        td = FakeTodoist([task("a")])
        self.run_once(td, write_comments=True)
        # 判断履歴からコメントの記録だけ消えた（別の実行環境など）→ Todoist 側を見て書かない
        doc = json.loads(self.paths.history.read_text(encoding="utf-8"))
        doc["tasks"]["a"].pop("comment_318")
        doc["tasks"]["a"]["snapshot"]["priority"] = "9"
        self.paths.history.write_text(json.dumps(doc), encoding="utf-8")
        run = self.run_once(td, now=NOW + timedelta(hours=1), write_comments=True)
        self.assertEqual(run["comments"]["already_there"], 1)
        self.assertEqual(len(td.posts), 1)

    def test_precheck_read_failure_means_no_post(self):
        td = FakeTodoist([task("a")])
        td.fail_reads["a"] = 2  # 本体の読取は通り、投稿前の重複確認で読めない
        run = self.run_once(td, write_comments=True)
        self.assertEqual(td.posts, [])
        self.assertEqual(run["comments"]["precheck_failed"], 1)
        self.assertEqual(run["result"], "partial")

    def test_writeahead_failure_means_no_post(self):
        td = FakeTodoist([task("a")])
        real = tr.atomic_write_json
        calls = {"n": 0}

        def flaky(path, data):
            if path.name == "history.json":
                calls["n"] += 1
                if calls["n"] == 2:  # 1 回目は通常の保存、2 回目が「送信中」の先書き
                    raise OSError("disk")
            return real(path, data)

        with mock.patch.object(tr, "atomic_write_json", side_effect=flaky):
            run = self.run_once(td, write_comments=True)
        self.assertEqual(td.posts, [])
        self.assertTrue(any(e.get("where") == "comment_writeahead" for e in run["errors"]))

    def test_cap_per_run(self):
        td = FakeTodoist([task(str(i)) for i in range(5)])
        run = self.run_once(td, write_comments=True)
        self.assertEqual(len(td.posts), 5)
        # 上限そのもの（cap）を直接確かめる
        out_run = {"run_id": "r", "tasks": [{"task_id": str(i), "category": "2", "comment_draft": f"【318】要判断\n要約: {i}\n処理ID: r"} for i in range(3)],
                   "errors": [], "writes": {"todoist": 0}}
        td2 = FakeTodoist([])
        cm.write_comments(out_run, {}, {"0", "1", "2"}, lambda p: td2.get(p)["results"], td2, lambda: None, NOW, cap=2)
        self.assertEqual(len(td2.posts), 2)
        self.assertEqual(out_run["comments"]["capped"], 1)
        self.assertEqual(run["writes"]["todoist"], 5)


class UnknownResponseTest(P3Base):
    def test_timeout_but_posted_is_reconciled_not_resent(self):
        td = FakeTodoist([task("a")])
        td.mode = "timeout_posted"
        run1 = self.run_once(td, write_comments=True)
        self.assertEqual(run1["result"], "partial")
        self.assertEqual(run1["comments"]["unknown"], 1)
        self.assertEqual(self.c318("a")["state"], "unknown")
        td.mode = "ok"
        run2 = self.run_once(td, now=NOW + timedelta(hours=1), write_comments=True)
        self.assertEqual(run2["comments"]["reconciled_posted"], 1)
        self.assertEqual(len(td.posts), 1)  # 再送していない
        self.assertEqual(self.c318("a")["state"], "posted")

    def test_timeout_lost_is_resent_after_reconcile(self):
        td = FakeTodoist([task("a")])
        td.mode = "timeout_lost"
        run1 = self.run_once(td, write_comments=True)
        td.mode = "ok"
        run2 = self.run_once(td, now=NOW + timedelta(hours=1), write_comments=True)
        self.assertEqual(run2["comments"]["reconciled_missing"], 1)
        self.assertEqual(run2["comments"]["retried"], 1)
        self.assertEqual(len(td.posts), 2)
        self.assertTrue(cm.has_run_id(td.posts[1][1], run1["run_id"]))  # 同じ処理ID のまま再送
        self.assertEqual(len(td.comments["a"]), 1)  # Todoist には 1 件だけ

    def test_unknown_stays_when_cannot_verify(self):
        td = FakeTodoist([task("a")])
        td.mode = "http503"
        self.run_once(td, write_comments=True)
        td.mode = "ok"
        td.fail_reads["a"] = td.reads["a"] + 1  # 次の回はコメントが読めない
        run2 = self.run_once(td, now=NOW + timedelta(hours=1), write_comments=True)
        self.assertEqual(run2["comments"]["unverified"], 1)
        self.assertEqual(len(td.posts), 1)
        self.assertEqual(self.c318("a")["state"], "unknown")

    def test_no_id_in_response_is_unknown(self):
        td = FakeTodoist([task("a")])
        td.mode = "noid"
        run = self.run_once(td, write_comments=True)
        self.assertEqual(run["comments"]["unknown"], 1)

    def test_definite_failure_retries_then_gives_up(self):
        td = FakeTodoist([task("a")])
        td.mode = "http400"
        run1 = self.run_once(td, write_comments=True)
        self.assertEqual(run1["comments"]["failed"], 1)
        self.assertEqual(self.c318("a")["state"], "failed")
        for k in (1, 2):
            self.run_once(td, now=NOW + timedelta(hours=k), write_comments=True)
        self.assertEqual(self.c318("a")["attempts"], 3)
        run4 = self.run_once(td, now=NOW + timedelta(hours=3), write_comments=True)
        self.assertEqual(self.c318("a")["state"], "gave_up")
        self.assertEqual(run4["comments"]["gave_up"], 1)
        self.assertEqual(len(td.posts), 3)
        td.mode = "ok"
        self.run_once(td, now=NOW + timedelta(hours=4), write_comments=True)
        self.assertEqual(len(td.posts), 3)  # 人が確かめるまで再送しない


class Guard317Test(P3Base):
    def test_317_skips_318_comments(self):
        td = FakeTodoist([task("a")])
        self.run_once(td, write_comments=True)
        body = td.posts[0][1]
        self.assertTrue(wh.is_agent_comment(body))
        self.assertTrue(cd.is_agent_comment(body))
        self.assertEqual(cm.guard_317(), "")

    def test_unverified_317_exclusion_stops_comments(self):
        td = FakeTodoist([task("a")])
        # 317 が 318 を除外しない状態（接頭辞もヘッダ判定も外れた）を作る
        with mock.patch.object(wh, "AGENT_COMMENT_PREFIXES", ("【別】",)), mock.patch.object(
            wh, "_AGENT_HEADER_RE", re.compile(r"^【別】")
        ):
            run = self.run_once(td, write_comments=True)
        self.assertEqual(td.posts, [])
        self.assertFalse(run["comments"]["enabled"])
        self.assertEqual(run["result"], "partial")

    def test_writer_has_only_comment_append(self):
        w = cm.TodoistCommentWriter("dummy")
        for name in ("close", "complete", "delete", "update", "reschedule", "update_task"):
            self.assertFalse(hasattr(w, name), name)
        with self.assertRaises(ValueError):
            w.post_comment("a", "題を書き換える")
        self.assertEqual(w.calls, 0)


class PlannedActionTest(P3Base):
    def test_ai_one_records_plan_but_does_not_execute(self):
        td = FakeTodoist([task("a", content="資料の下調べ")])
        self.run_once(td, dry=True, emit_packet=True)
        sid = json.loads(self.paths.packet.read_text(encoding="utf-8"))["tasks"][0]["snapshot_id"]
        ans = {"a": {"category": "1", "reason": "調べてまとめるだけ", "snapshot_id": sid, "plan": "公開資料を3つ読んで要点を下書き"}}
        run = self.run_once(td, ai_answers=ans, write_comments=True)
        e = [x for x in run["tasks"] if x["task_id"] == "a"][0]
        self.assertEqual(e["category"], "1")
        self.assertFalse(e["planned_action"]["executed"])
        self.assertEqual(e["planned_action"]["plan"], "公開資料を3つ読んで要点を下書き")
        self.assertNotIn("ai_plan", e)
        body = td.posts[0][1]
        self.assertTrue(body.startswith("【318】途中"))
        self.assertIn("自律実行はまだ動かしていない", body)
        self.assertIn("公開資料を3つ読んで要点を下書き", body)
        self.assertEqual(run["writes"]["todoist"], 1)  # コメント以外の書き込みは無い

    def test_rule_one_gets_default_plan(self):
        td = FakeTodoist([task("a", content="🤖 ログの整理")])
        run = self.run_once(td)
        e = run["tasks"][0]
        self.assertEqual(e["category"], "1")
        self.assertEqual(e["planned_action"]["plan_by"], "default")
        self.assertIn("まだ実行しない", e["proposal"])


class MorningSlotTest(P3Base):
    def test_schedule_waits_until_owner_is_318(self):
        td = FakeTodoist([task("a")])
        run = self.run_once(td, now=AT_1030, trigger="schedule")
        self.assertEqual(run["result"], "stopped")
        self.assertEqual(run["stop_code"], "morning_not_owner")
        self.assertEqual(td.paths, [])  # Todoist を読んでいない
        # 見送った回は「過去の本実行」に数えない（履歴が無くても次の回は初回として動く）
        ms.set_owner(self.state, "318")
        run = self.run_once(td, now=AT_1030 + timedelta(days=1), trigger="schedule")
        self.assertEqual(run["result"], "success")

    def test_schedule_runs_when_owner_is_318(self):
        ms.set_owner(self.state, "318")
        td = FakeTodoist([task("a")])
        run = self.run_once(td, now=AT_1030, trigger="schedule")
        self.assertEqual(run["result"], "success")
        self.assertEqual(run["trigger"], "schedule")
        self.assertIsNone(ms.read_lock(self.state))  # 終わったら朝枠を返す

    def test_manual_still_avoids_313_window(self):
        ms.set_owner(self.state, "318")
        run = self.run_once(FakeTodoist([]), now=AT_1030)
        self.assertEqual(run["stop_code"], "overlap_313_window")

    def test_313_trace_blocks_318(self):
        ms.set_owner(self.state, "318")
        self.t313.write_text("[]", encoding="utf-8")  # 313 0.5 が今まさに作業ファイルを書いた
        ts = AT_1030.timestamp()
        os.utime(self.t313, (ts, ts))
        td = FakeTodoist([task("a")])
        run = self.run_once(td, now=AT_1030 + timedelta(minutes=5), trigger="schedule")
        self.assertEqual(run["stop_code"], "morning_busy")
        self.assertEqual(run["result"], "failed")
        self.assertEqual(td.paths, [])
        # 90 分たった跡は見ない
        run = self.run_once(td, now=AT_1030 + timedelta(minutes=100), trigger="schedule")
        self.assertEqual(run["result"], "success")

    def test_313_lock_blocks_318_and_318_lock_blocks_313(self):
        ms.acquire(self.state, "313", "x313", now=AT_1030, pid=os.getpid())
        run = self.run_once(FakeTodoist([]))
        self.assertEqual(run["stop_code"], "morning_busy")
        ms.release(self.state, "x313")
        ms.acquire(self.state, "318", "r1", now=NOW, pid=os.getpid())
        self.assertEqual(ms.check(self.state, "313", scheduled=True, now=NOW)[0], "busy")

    def test_313_stops_when_owner_moved(self):
        self.assertEqual(ms.check(self.state, "313", scheduled=True, now=AT_1030), ("", ""))
        ms.set_owner(self.state, "318")
        self.assertEqual(ms.check(self.state, "313", scheduled=True, now=AT_1030)[0], "not_owner")
        self.assertEqual(ms.main(["--state-dir", str(self.state), "check", "--who", "313"]), 3)
        ms.set_owner(self.state, "313")  # 戻し
        self.assertEqual(ms.main(["--state-dir", str(self.state), "check", "--who", "313"]), 0)

    def test_stale_lock_is_cleared(self):
        old = NOW - timedelta(hours=3)
        ms.lock_path(self.state).write_text(json.dumps({"who": "313", "run_id": "old", "pid": 999999, "started_at": old.isoformat()}))
        run = self.run_once(FakeTodoist([]))
        self.assertEqual(run["result"], "success")

    def test_broken_owner_file_fails_safe(self):
        ms.owner_path(self.state).write_text("{broken", encoding="utf-8")
        run = self.run_once(FakeTodoist([]), now=AT_1030, trigger="schedule")
        self.assertEqual(run["stop_code"], "morning_owner_unreadable")
        self.assertEqual(run["result"], "failed")

    def test_set_owner_needs_yes(self):
        self.assertEqual(ms.main(["--state-dir", str(self.state), "set-owner", "--who", "318"]), 2)
        self.assertEqual(ms.get_owner(self.state), "313")


class LaunchdTemplateTest(unittest.TestCase):
    LA = REPO / "launchd"

    def test_template_is_10_30_and_not_run_at_load(self):
        raw = (self.LA / "com.matsunoma.jarvis.todoist-318.plist.template").read_text(encoding="utf-8")
        d = plistlib.loads(raw.replace("__REPO__", "/r").replace("__HOME__", "/h").encode("utf-8"))
        self.assertEqual(d["Label"], "com.matsunoma.jarvis.todoist-318")
        self.assertEqual(d["StartCalendarInterval"], {"Hour": 10, "Minute": 30})
        self.assertFalse(d.get("RunAtLoad", False))
        self.assertIn("jarvis_todoist_318_runner.sh", " ".join(d["ProgramArguments"]))

    def test_runner_uses_schedule_trigger_and_no_write_flags(self):
        s = (self.LA / "jarvis_todoist_318_runner.sh").read_text(encoding="utf-8")
        self.assertIn("--trigger schedule", s)
        for flag in ("--publish", "--send-slack", "--write-comments"):
            self.assertNotIn(f"run {flag}", s)
        self.assertIn("TODOIST_318_RUN_FLAGS", s)

    def test_install_refuses_without_confirmation(self):
        r = subprocess.run(["bash", str(self.LA / "install_jarvis_todoist_318_launchd.sh")],
                           capture_output=True, text=True, timeout=30, env={**os.environ, "HOME": tempfile.mkdtemp()})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--yes", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
