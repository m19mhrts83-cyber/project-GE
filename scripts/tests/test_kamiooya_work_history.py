import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from unittest.mock import patch, Mock
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("work_history", Path(__file__).parents[1] / "jarvis_kamiooya_work_history.py")
work = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(work)


class WorkHistoryTest(unittest.TestCase):
    def sample(self, event_id="original"):
        return {"version":1,"updated_at":"2026-11-01T12:00:00+09:00","projects":[{"id":"p","title":"案件","items":[{"id":"a","title":"項目","status":"planned"}],"events":[{"id":event_id,"item_id":"a","at":"2026-11-01T12:00:00+09:00","kind":"log","summary":"記録","actor":"Chappy","minutes":None,"time_kind":"unrecorded","evidence":[]}]}]}

    def test_merge_keeps_dashboard_entry_and_rejects_conflicting_corrections(self):
        local = self.sample()
        remote = self.sample("web")
        combined = work.merge(local,remote)
        self.assertEqual({e["id"] for e in combined["projects"][0]["events"]},{"original","web"})
        remote["projects"][0]["events"][0]["supersedes"]="original"
        local["projects"][0]["events"].append({**local["projects"][0]["events"][0],"id":"local-edit","supersedes":"original"})
        with self.assertRaisesRegex(ValueError,"訂正が競合"):
            work.merge(local,remote)

    def test_push_retries_compare_and_swap_and_merges_new_remote_entry(self):
        local = self.sample()
        first = {"value":json.dumps(self.sample()),"updated_at":"2026-11-01T03:00:00Z"}
        second = {"value":json.dumps(self.sample("web")),"updated_at":"2026-11-01T03:01:00Z"}
        empty = Mock(ok=True,status_code=200); empty.json.return_value=[]
        success = Mock(ok=True,status_code=200); success.json.return_value=[{"key":"kamiooya_work_history"}]
        with patch.object(work,"remote_config",return_value=("https://example.com/rest/v1/sync_meta",{})), patch.object(work,"remote_read",side_effect=[first,second]), patch("requests.patch",side_effect=[empty,success]) as save:
            combined=work.push(local)
        self.assertEqual(save.call_count,2)
        self.assertEqual(save.call_args.kwargs["params"]["updated_at"],"eq."+second["updated_at"])
        self.assertEqual({e["id"] for e in combined["projects"][0]["events"]},{"original","web"})

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
