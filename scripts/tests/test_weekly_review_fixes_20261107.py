# -*- coding: utf-8 -*-
"""314 週次レビュー 2026-11-07 の修正テスト。

① glucon watch: Realtime 購読中は保険の間隔、Supabase 失敗中は倍々で最大 300 秒
   sync_meta への heartbeat は 300 秒に1回
② 機械チェック: 前回の本番実行で読んだ位置から後だけ数える／最後に出た時刻を付ける
③ kamiooya-qa release workflow に permissions: contents: read
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


class GluconWatchBackoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.w = _load("forum_watch", "scripts/jarvis_westudy_forum_post_watch.py")
        self.w.POLL_SEC = 3
        self.w.FALLBACK_POLL_SEC = 30
        self.w._sb_fail_streak = 0
        self.w._realtime_ok = False

    def test_realtime_down_uses_short_poll(self) -> None:
        self.assertEqual(self.w.next_poll_delay(), 3.0)

    def test_realtime_up_uses_fallback_poll(self) -> None:
        self.w._realtime_ok = True
        self.assertEqual(self.w.next_poll_delay(), 30.0)

    def test_failures_back_off_up_to_cap(self) -> None:
        self.w._note_sb(False)
        self.assertEqual(self.w.next_poll_delay(), 6.0)
        for _ in range(20):
            self.w._note_sb(False)
        self.assertEqual(self.w.next_poll_delay(), 300.0)
        self.w._note_sb(True)
        self.assertEqual(self.w.next_poll_delay(), 3.0)

    def test_queued_count_failure_counts_streak(self) -> None:
        class Boom:
            def table(self, _name):
                raise RuntimeError("402 restricted")

        with mock.patch.object(self.w, "sb_client", return_value=Boom()):
            self.assertEqual(self.w.queued_count(), 0)
        self.assertEqual(self.w._sb_fail_streak, 1)

    def test_db_heartbeat_throttled(self) -> None:
        calls: list[str] = []

        class Sb:
            def table(self, name):
                calls.append(name)
                return self

            def upsert(self, _row):
                return self

            def execute(self):
                return None

        with tempfile.TemporaryDirectory() as td:
            self.w.STATE_PATH = Path(td) / "state.json"
            self.w._last_db_heartbeat = 0.0
            with mock.patch.object(self.w, "sb_client", return_value=Sb()):
                self.w.write_heartbeat()
                self.w.write_heartbeat()
                self.w.write_heartbeat()
            self.assertEqual(calls, ["sync_meta"])
            self.assertTrue(self.w.STATE_PATH.is_file())

    def test_db_heartbeat_skipped_while_failing(self) -> None:
        calls: list[str] = []

        class Sb:
            def table(self, name):
                calls.append(name)
                raise AssertionError("should not call")

        with tempfile.TemporaryDirectory() as td:
            self.w.STATE_PATH = Path(td) / "state.json"
            self.w._last_db_heartbeat = 0.0
            self.w._sb_fail_streak = 2
            with mock.patch.object(self.w, "sb_client", return_value=Sb()):
                self.w.write_heartbeat()
            self.assertEqual(calls, [])


class WeeklyReviewOffsetsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _load("wr314", "scripts/jarvis_weekly_review_314.py")

    def test_counts_only_new_lines_after_saved_offset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "Logs"
            d = root / "jarvis_demo"
            d.mkdir(parents=True)
            log = d / "x.log"
            log.write_text("OSError: boom\n" * 10, encoding="utf-8")
            offs = Path(td) / "offsets.json"
            since = datetime.now(self.m.JST) - timedelta(days=7)

            rows = self.m.collect_launchd_logs(since, log_root=root, offsets_path=offs, save_offsets=True)
            self.assertEqual(rows[0]["repeated"][0]["count"], 10)
            self.assertIn("last", rows[0]["repeated"][0])
            self.assertTrue(offs.is_file())

            # 何も増えていなければ 0（=要確認に載らない）
            rows = self.m.collect_launchd_logs(since, log_root=root, offsets_path=offs)
            self.assertEqual(rows, [])

            with log.open("a", encoding="utf-8") as fh:
                fh.write("OSError: boom\n" * 6)
            rows = self.m.collect_launchd_logs(since, log_root=root, offsets_path=offs)
            self.assertEqual(rows[0]["repeated"][0]["count"], 6)

    def test_dry_run_does_not_move_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "Logs"
            d = root / "jarvis_demo"
            d.mkdir(parents=True)
            (d / "x.log").write_text("FAIL x\n" * 7, encoding="utf-8")
            offs = Path(td) / "offsets.json"
            since = datetime.now(self.m.JST) - timedelta(days=7)
            self.m.collect_launchd_logs(since, log_root=root, offsets_path=offs, save_offsets=False)
            self.assertFalse(offs.exists())
            rows = self.m.collect_launchd_logs(since, log_root=root, offsets_path=offs)
            self.assertEqual(rows[0]["repeated"][0]["count"], 7)

    def test_truncated_log_is_read_from_start(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "Logs"
            d = root / "jarvis_demo"
            d.mkdir(parents=True)
            log = d / "x.log"
            log.write_text("FAIL a\n" * 20, encoding="utf-8")
            offs = Path(td) / "offsets.json"
            since = datetime.now(self.m.JST) - timedelta(days=7)
            self.m.collect_launchd_logs(since, log_root=root, offsets_path=offs, save_offsets=True)
            log.write_text("FAIL a\n" * 5, encoding="utf-8")  # 作り直し（短くなった）
            rows = self.m.collect_launchd_logs(since, log_root=root, offsets_path=offs)
            self.assertEqual(rows[0]["repeated"][0]["count"], 5)

    def test_flag_shows_last_seen(self) -> None:
        facts = {
            "gha": {"failures": [], "schedule_delay": []},
            "launchd": [{"dir": "jarvis_demo", "repeated": [{"msg": "FAIL", "count": 9, "last": "11-07 08:00"}]}],
            "tests": {"failed": []},
            "deps_missing": [],
            "commits": {"ai_call_adds": []},
        }
        flags = self.m.build_flags(facts)
        self.assertTrue(any("最後 11-07 08:00" in f for f in flags), flags)


class ReleaseWorkflowPermissionsTest(unittest.TestCase):
    def test_contents_read_only(self) -> None:
        text = (REPO / ".github" / "workflows" / "kamiooya-qa-release.yml").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^permissions:\n  contents: read$")


if __name__ == "__main__":
    unittest.main()
