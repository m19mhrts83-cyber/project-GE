#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from jarvis_openchat_recover_worker import running_is_stale  # noqa: E402
from jarvis_openchat_thread_health import evaluate_route  # noqa: E402


def route(*, registered: int) -> dict:
    return {
        "id": "sample",
        "org_label": "sample",
        "include_threads": True,
        "thread_mids": [f"t{i}" for i in range(registered)],
    }


class OpenchatHealthTest(unittest.TestCase):
    def test_main_only_is_not_attention(self) -> None:
        result = evaluate_route(
            route(registered=0),
            {"appended_main": 2, "appended_threads": 0, "ok": 0},
            {},
            {"main": 2, "thread": 0, "reply": 0},
            {"main": 2, "thread": 0, "reply": 0},
            0,
        )
        self.assertEqual(result["level"], "info")
        self.assertEqual(result["symptom"], "main_only_no_thread_evidence")

    def test_unregistered_active_notification_is_attention(self) -> None:
        history = {
            f"2026-10-{day:02d}": {
                "routes": {"sample": {"appended_threads": 0, "appended_main": 1}}
            }
            for day in range(1, 8)
        }
        result = evaluate_route(
            route(registered=2),
            {"appended_main": 1, "appended_threads": 0, "ok": 2},
            history,
            {"main": 1, "thread": 0, "reply": 0},
            {"main": 1, "thread": 0, "reply": 0},
            1,
        )
        self.assertEqual(result["level"], "attention")

    def test_recent_reply_prevents_dormant_attention(self) -> None:
        result = evaluate_route(
            route(registered=2),
            {"appended_main": 1, "appended_threads": 0, "ok": 1},
            {},
            {"main": 1, "thread": 0, "reply": 1},
            {"main": 1, "thread": 0, "reply": 1},
            0,
        )
        self.assertEqual(result["level"], "ok")

    def test_old_running_recipe_is_stale(self) -> None:
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        self.assertTrue(
            running_is_stale(
                {"status": "running", "started_at": (now - timedelta(hours=3)).isoformat()},
                now=now,
            )
        )
        self.assertFalse(
            running_is_stale(
                {"status": "running", "started_at": (now - timedelta(minutes=30)).isoformat()},
                now=now,
            )
        )


if __name__ == "__main__":
    unittest.main()
