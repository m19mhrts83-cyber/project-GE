from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_todoist_313_done_elsewhere as m  # noqa: E402

NOW = datetime(2026, 11, 25, 19, 30, tzinfo=timezone(timedelta(hours=9)))


def row(tid: str) -> dict:
    return {
        "n": 1, "task_id": tid, "title": f"タスク{tid}", "labels": ["x"], "confidence": "low", "streak_days": 2,
        "evidence": [{"folder": "P01_相手", "path": "/Users/secret/5.やり取り.md", "subject": "件名", "mtime": "2026-11-24T10:00:00+09:00"}],
    }


class CloseLeakSnapshot(unittest.TestCase):
    def test_no_local_path_and_held_excluded(self):
        d = m.snapshot_doc([row("1"), row("2")], now=NOW, held={"2"})
        self.assertEqual(d["total"], 1)
        self.assertEqual([c["id"] for c in d["cards"]], ["1"])
        ev = d["cards"][0]["evidence"][0]
        self.assertNotIn("path", ev)
        self.assertEqual(ev["folder"], "P01_相手")
        self.assertEqual(d["generated_at"], "2026-11-25T19:30:00+09:00")

    def test_empty(self):
        d = m.snapshot_doc([], now=NOW, held=set())
        self.assertEqual((d["total"], d["cards"]), (0, []))


if __name__ == "__main__":
    unittest.main()
