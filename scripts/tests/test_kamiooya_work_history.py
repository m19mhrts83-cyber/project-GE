import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("work_history", Path(__file__).parents[1] / "jarvis_kamiooya_work_history.py")
work = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(work)


class WorkHistoryTest(unittest.TestCase):
    def test_records_questions_answers_without_duplicate_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            def run(*args):
                with contextlib.redirect_stdout(io.StringIO()):
                    return work.main(["--file", str(path), *args])
            run("plan", "--project", "p", "--title", "案件", "--item", "a:保存確認")
            run("ask", "--project", "p", "--item", "a", "--summary", "本人の操作時間？", "--event-id", "q")
            args = ("answer", "--project", "p", "--item", "a", "--summary", "20分", "--question-id", "q", "--event-id", "a", "--minutes", "20", "--time-kind", "owner_confirmed")
            run(*args)
            run(*args)
            data = work.load(path)
            events = data["projects"][0]["events"]
            self.assertEqual(len(events), 2)
            self.assertIsNone(events[0]["minutes"])
            self.assertEqual(events[1]["question_id"], "q")
            self.assertEqual(events[1]["minutes"], 20)
            with self.assertRaises(ValueError):
                run("answer", "--project", "p", "--item", "a", "--summary", "重複", "--question-id", "q")
            with self.assertRaises(ValueError):
                run("log", "--project", "p", "--item", "a", "--summary", "未分類", "--minutes", "20")
            self.assertEqual(len(work.load(path)["projects"][0]["events"]), 2)
            self.assertIn("時間: 未記録", path.with_suffix(".md").read_text())

    def test_corrupt_history_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text('{"broken":', encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                work.main(["--file", str(path), "show"])
            self.assertEqual(path.read_text(), '{"broken":')


if __name__ == "__main__":
    unittest.main()
