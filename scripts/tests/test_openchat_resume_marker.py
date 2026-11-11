#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from jarvis_openchat_thread_health import evaluate_resume_marker  # noqa: E402

MARKER_TEXT = "2026-11-10 20:31:27 +0900 監視のresumeに失敗（トークン失効/QR要の可能性）\n"


class ResumeMarkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.marker = Path(self.tmp.name) / "WATCH_RESUME_FAILED.txt"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def watch(self, **over: object) -> dict:
        base = {"state": "running", "started_at": "2026-11-11T02:46:19+09:00"}
        base.update(over)
        return base

    def test_no_marker_is_ok(self) -> None:
        self.assertEqual(evaluate_resume_marker(self.marker, self.watch(), 10), ("ok", None))

    def test_recovered_after_marker_is_info(self) -> None:
        self.marker.write_text(MARKER_TEXT, encoding="utf-8")
        level, note = evaluate_resume_marker(self.marker, self.watch(), 10)
        self.assertEqual(level, "info")
        self.assertEqual(note, "前回 2026-11-10 20:31 に再開失敗 → いまは復帰済み")

    def test_started_before_marker_stays_attention(self) -> None:
        self.marker.write_text(MARKER_TEXT, encoding="utf-8")
        level, _ = evaluate_resume_marker(
            self.marker, self.watch(started_at="2026-11-10T19:00:00+09:00"), 10
        )
        self.assertEqual(level, "attention")

    def test_stale_heartbeat_stays_attention(self) -> None:
        self.marker.write_text(MARKER_TEXT, encoding="utf-8")
        self.assertEqual(evaluate_resume_marker(self.marker, self.watch(), 600)[0], "attention")
        self.assertEqual(evaluate_resume_marker(self.marker, self.watch(), None)[0], "attention")

    def test_not_running_stays_attention(self) -> None:
        self.marker.write_text(MARKER_TEXT, encoding="utf-8")
        level, _ = evaluate_resume_marker(self.marker, self.watch(state="stopped"), 10)
        self.assertEqual(level, "attention")

    def test_unparsable_marker_falls_back_to_mtime(self) -> None:
        self.marker.write_text("broken\n", encoding="utf-8")
        # mtime は今なので、それより前に起動した監視は復帰扱いにしない
        level, _ = evaluate_resume_marker(self.marker, self.watch(), 10)
        self.assertEqual(level, "attention")


if __name__ == "__main__":
    unittest.main()
