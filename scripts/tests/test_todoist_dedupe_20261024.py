#!/usr/bin/env python3
"""部長ボックス todoist_tasks の二重反映防止（2026-10-19 に同一タスク 5 件）の単体テスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_hawk_todoist_tasks_apply as hawk  # noqa: E402
import jarvis_todoist_api as api  # noqa: E402

MD = """---
action: todoist_tasks
source: hawk
---

## create
- lane: inbox
  title: [要ボス] WT・太田慎二さんの定着
  due: 2026-10-25
- lane: inbox
  title: もう1件
"""


class FindOpenDuplicateTests(unittest.TestCase):
    TASKS = [
        {"id": "1", "content": "[要ボス] WT・太田慎二さんの定着 ", "due": {"date": "2026-10-25"}},
        {"id": "2", "content": "期日なし", "due": None},
    ]

    def test_same_title_same_iso_due(self):
        self.assertEqual(api.find_open_duplicate(self.TASKS, "[要ボス] WT・太田慎二さんの定着", "2026-10-25")["id"], "1")

    def test_different_iso_due_is_not_duplicate(self):
        self.assertIsNone(api.find_open_duplicate(self.TASKS, "[要ボス] WT・太田慎二さんの定着", "2026-11-01"))

    def test_natural_or_no_due_matches_title(self):
        self.assertEqual(api.find_open_duplicate(self.TASKS, "期日なし", None)["id"], "2")
        self.assertEqual(api.find_open_duplicate(self.TASKS, "期日なし", "tomorrow")["id"], "2")

    def test_other_title(self):
        self.assertIsNone(api.find_open_duplicate(self.TASKS, "別のタスク", None))


class LedgerTests(unittest.TestCase):
    def run_apply(self, md: Path, ledger: dict, results: list[dict]):
        calls: list[list[str]] = []

        def fake(args, dry_run):
            calls.append(args)
            return results.pop(0) if results else {"ok": True}

        with mock.patch.object(hawk, "_run_api", side_effect=fake):
            rep = hawk.apply_file(md, dry_run=False, ledger=ledger)
        return rep, calls

    def test_rerun_after_partial_failure_does_not_recreate_success(self):
        with tempfile.TemporaryDirectory() as d:
            md = Path(d) / "2026-10-19_hawk_tasks.md"
            md.write_text(MD, encoding="utf-8")
            ledger: dict = {}
            rep1, calls1 = self.run_apply(md, ledger, [{"ok": True}, {"ok": False, "error": "x"}])
            self.assertFalse(rep1["ok"])  # 1 件失敗 → MD は残る
            self.assertEqual(len(calls1), 2)
            rep2, calls2 = self.run_apply(md, ledger, [{"ok": True}])
            self.assertTrue(rep2["ok"])
            self.assertEqual(len(calls2), 1)  # 成功済みの 1 件目は作り直さない
            self.assertIn("もう1件", " ".join(calls2[0]))
            rep3, calls3 = self.run_apply(md, ledger, [])
            self.assertEqual(calls3, [])  # 3 回目は何もしない

    def test_ledger_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(hawk, "LEDGER_PATH", Path(d) / "l.json"):
                hawk.save_ledger({"a.md": {"create|inbox|x": "2026-10-24T00:00:00+00:00"}})
                self.assertEqual(hawk.load_ledger(), {"a.md": {"create|inbox|x": "2026-10-24T00:00:00+00:00"}})


class LockTests(unittest.TestCase):
    def test_second_runner_skips(self):
        import fcntl

        with tempfile.TemporaryDirectory() as d:
            lock = Path(d) / "x.lock"
            fh = open(lock, "w")
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with mock.patch.object(hawk, "LOCK_PATH", lock), \
                    mock.patch.object(sys, "argv", ["x", "--apply"]), \
                    mock.patch.object(hawk, "folder", side_effect=AssertionError("should not read inbox")):
                self.assertEqual(hawk.main(), 0)
            fh.close()


if __name__ == "__main__":
    unittest.main()
