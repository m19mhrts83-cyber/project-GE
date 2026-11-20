import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import os
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("inbox", SCRIPTS / "jarvis_obsidian_review_inbox.py")
inbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inbox)


class MonthlyJournalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = Path(self.tmp.name)
        self.patcher = patch.object(inbox, "VAULT", self.vault)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.item = dict(review_id="745b07d2-9a30-4cc7-b7cf-9110c14f8e64",
                         review_date="2026-11-12", raw_log="生ログ  \n\n", tactical_review="レビュー")

    def test_month_boundary_and_body_preservation(self):
        paths = inbox.write_review(self.item)
        self.assertEqual(paths, ["01_Journaling/★Journal/2026-11/2026-11-12.md"])
        text = (self.vault / paths[0]).read_text()
        self.assertIn("## 生ログ\n\n" + self.item["raw_log"] + "\n\n## 戦術レビュー", text)
        self.assertIn(self.item["tactical_review"], text)
        self.assertEqual(inbox.write_review({**self.item, "review_date": "2026-12-01"}),
                         ["01_Journaling/★Journal/2026-12/2026-12-01.md"])

    def test_retry_is_safe_and_different_content_never_overwrites(self):
        path = self.vault / inbox.write_review(self.item)[0]
        original = path.read_bytes()
        inbox.write_review(self.item)
        with self.assertRaises(inbox.InboxError):
            inbox.write_review({**self.item, "tactical_review": "別の内容"})
        self.assertEqual(path.read_bytes(), original)

    def test_symlink_parent_rejected_without_creating_outside_directory(self):
        outside = self.vault / "outside"
        outside.mkdir()
        (self.vault / "01_Journaling").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(inbox.InboxError):
            inbox.write_review(self.item)
        self.assertEqual(list(outside.iterdir()), [])

    def test_reads_only_holds_reviews_but_returns_search_results(self):
        request = {"id": "745b07d2-9a30-4cc7-b7cf-9110c14f8e65",
                   "request_type": "search", "request_payload": {"query": "example"}}
        calls = []

        def api(url, key, **kwargs):
            calls.append((url, kwargs))
            if kwargs.get("method", "GET") == "GET":
                return {"items": [self.item], "vault_read_items": [request]}
            return {"ok": True}

        with patch.dict(os.environ, {"OBSIDIAN_REVIEW_POLL_KEY": "poll", "OBSIDIAN_VAULT_POLL_KEY": "read"}), \
             patch.object(sys, "argv", ["inbox", "--reads-only"]), \
             patch.object(inbox, "api_request", side_effect=api), \
             patch.object(inbox, "process_request", return_value={"result_count": 0}), \
             patch.object(inbox, "write_review", side_effect=AssertionError("review write forbidden")):
            self.assertEqual(inbox.main(), 0)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[1][0].endswith("/api/obsidian-vault/inbox"))
        self.assertEqual(calls[1][1]["payload"]["request_id"], request["id"])
        self.assertEqual(list(self.vault.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
