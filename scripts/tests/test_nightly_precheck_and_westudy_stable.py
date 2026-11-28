# -*- coding: utf-8 -*-
"""300室 夜のまとめの precheck（共通部品込み）と WeStudy 監視の自動終了のテスト。"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 28, 21, 5, tzinfo=JST)

import jarvis_nightly_precheck_lib as lib  # noqa: E402
import jarvis_room300_nightly_precheck as pc  # noqa: E402
import jarvis_westudy_weekly_check as ws  # noqa: E402


def _stall(rows, checked="2026-11-28T18:20:00+09:00"):
    return {"checked_at": checked, "rows": rows}


def _row(i, st="ok", stop="ok", idle="skip"):
    return {"id": i, "status": st, "stop_status": stop, "idle_status": idle, "why": "x"}


class Room300PrecheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.td = Path(tempfile.mkdtemp())
        self.stall = self.td / "stall.json"
        self.runs = self.td / "runs"
        self.runs.mkdir()
        self.state = self.td / "state.json"
        self.patches = [
            mock.patch.object(pc, "STALL", self.stall),
            mock.patch.object(pc, "RUNS_318", self.runs),
            mock.patch.object(pc, "ERR_LOGS", [self.td / "e.log"]),
            mock.patch.object(pc, "STATE_PATH", self.state),
            mock.patch.object(pc, "gha_failed_today", lambda *a, **k: ([], None)),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def run_pc(self, argv=None) -> int:
        return lib.run_precheck("room300", pc.collect, self.state, argv=argv or [], now=NOW)

    def test_normal_night_skips(self) -> None:
        self.stall.write_text(json.dumps(_stall([_row("311"), _row("313")])))
        self.assertEqual(self.run_pc(), lib.SKIP)
        self.assertEqual(json.loads(self.state.read_text())["last_verdict"], "skip")

    def test_missing_state_runs(self) -> None:
        self.assertEqual(self.run_pc(), lib.RUN)

    def test_stale_315b_runs(self) -> None:
        self.stall.write_text(json.dumps(_stall([_row("311")], checked="2026-11-27T18:20:00+09:00")))
        self.assertEqual(self.run_pc(), lib.RUN)

    def test_stale_row_runs(self) -> None:
        self.stall.write_text(json.dumps(_stall([_row("311", st="stale")])))
        self.assertEqual(self.run_pc(), lib.RUN)

    def test_unknown_only_second_night_runs(self) -> None:
        self.stall.write_text(json.dumps(_stall([_row("312", st="unknown", stop="unknown")])))
        self.assertEqual(self.run_pc(), lib.SKIP)  # 初回は記録だけ
        self.assertEqual(self.run_pc(), lib.RUN)  # 2晩続いたら起こす

    def test_318_failure_today_runs(self) -> None:
        self.stall.write_text(json.dumps(_stall([_row("311")])))
        (self.runs / "r318-x.json").write_text(json.dumps(
            {"run_id": "r318-x", "started_at": "2026-11-28T10:30:00+09:00", "mode": "live", "result": "failure", "errors": []}))
        self.assertEqual(self.run_pc(), lib.RUN)

    def test_318_old_failure_ignored(self) -> None:
        self.stall.write_text(json.dumps(_stall([_row("311")])))
        (self.runs / "r318-y.json").write_text(json.dumps(
            {"run_id": "r318-y", "started_at": "2026-11-27T10:30:00+09:00", "mode": "live", "result": "failure"}))
        self.assertEqual(self.run_pc(), lib.SKIP)

    def test_error_log_growth_runs_once(self) -> None:
        self.stall.write_text(json.dumps(_stall([_row("311")])))
        log = self.td / "e.log"
        log.write_text("")
        self.assertEqual(self.run_pc(), lib.SKIP)  # 初回は末尾から
        log.write_text("Traceback (most recent call last):\nValueError: x\n")
        self.assertEqual(self.run_pc(), lib.RUN)
        self.assertEqual(self.run_pc(), lib.SKIP)  # 位置が進むので同じ行で毎晩起こさない

    def test_gha_failure_runs_and_unreadable_only_yellow(self) -> None:
        self.stall.write_text(json.dumps(_stall([_row("311")])))
        with mock.patch.object(pc, "gha_failed_today", lambda *a, **k: (["1:failure"], None)):
            self.assertEqual(self.run_pc(), lib.RUN)
        with mock.patch.object(pc, "gha_failed_today", lambda *a, **k: ([], "TimeoutExpired")):
            self.assertEqual(self.run_pc(), lib.SKIP)

    def test_exception_fails_open(self) -> None:
        def boom(ctx):
            raise RuntimeError("x")
        self.assertEqual(lib.run_precheck("t", boom, self.state, argv=[], now=NOW), lib.RUN)

    def test_show_does_not_write_state(self) -> None:
        self.stall.write_text(json.dumps(_stall([_row("311")])))
        self.assertEqual(self.run_pc(["show"]), lib.RUN)
        self.assertFalse(self.state.exists())


class WestudyAutoStableTest(unittest.TestCase):
    def _runs(self, rid, conc="success"):
        return [{"databaseId": rid, "conclusion": conc, "status": "completed"}]

    def test_stable_after_two_new_successes(self) -> None:
        st = {"disabled": False, "consecutive_successes": 0, "last_run_id": 1, "last_conclusion": "failure"}
        ws.advance_state(st, self._runs(2), {}, now=NOW)
        self.assertFalse(st["disabled"])
        self.assertEqual(st["consecutive_successes"], 1)
        ws.advance_state(st, self._runs(2), {}, now=NOW)  # 同じ run は数えない
        self.assertEqual(st["consecutive_successes"], 1)
        ws.advance_state(st, self._runs(3), {}, now=NOW)
        self.assertTrue(st["disabled"])
        self.assertIn("auto_stable_at", st)

    def test_failure_resets(self) -> None:
        st = {"disabled": False, "consecutive_successes": 1, "last_run_id": 2}
        ws.advance_state(st, self._runs(3, "failure"), {}, now=NOW)
        self.assertEqual(st["consecutive_successes"], 0)
        self.assertFalse(st["disabled"])


if __name__ == "__main__":
    unittest.main()
