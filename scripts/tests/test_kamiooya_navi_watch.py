import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kamiooya_navi_watch as w  # noqa: E402


class JudgeTest(unittest.TestCase):
    def test_first_ok_is_up(self):
        self.assertEqual(w.judge((True, "HTTP 200"), None)[0], "up")

    def test_one_failure_then_ok_is_up(self):
        self.assertEqual(w.judge((False, "HTTP 502"), (True, "HTTP 200"))[0], "up")

    def test_two_failures_is_down(self):
        state, detail = w.judge((False, "HTTP 502"), (False, "TimeoutError"))
        self.assertEqual(state, "down")
        self.assertIn("502", detail)


class NextStatusTest(unittest.TestCase):
    now = datetime(2026, 11, 25, 7, 0, tzinfo=timezone.utc)

    def test_same_state_writes_nothing(self):
        self.assertIsNone(w.next_status({"state": "up"}, "up", "HTTP 200", self.now))

    def test_change_writes_jst_since(self):
        new = w.next_status({"state": "up"}, "down", "HTTP 502 / HTTP 502", self.now)
        self.assertEqual(new["state"], "down")
        self.assertEqual(new["since"], "2026-11-25T16:00+09:00")

    def test_recovery_message_mentions_start(self):
        prev = {"state": "down", "since": "2026-11-25T16:00+09:00"}
        new = w.next_status(prev, "up", "HTTP 200", self.now)
        self.assertIn("戻りました", w.slack_text(new, prev))
        self.assertIn("2026-11-25 16:00", w.slack_text(new, prev))


class LoadStatusTest(unittest.TestCase):
    def test_missing_file_means_up(self):
        self.assertEqual(w.load_status(Path(tempfile.gettempdir()) / "no-such-navi.json")["state"], "up")

    def test_bad_state_is_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"state": "maybe"}, f)
        with self.assertRaises(ValueError):
            w.load_status(Path(f.name))

    def test_repo_status_file_is_valid(self):
        self.assertIn(w.load_status()["state"], ("up", "down"))


class ProbeTest(unittest.TestCase):
    def test_4xx_counts_as_up(self):
        import urllib.error
        orig = w.urllib.request.urlopen
        def raise_404(*a, **k):
            raise urllib.error.HTTPError(w.APP_URL, 404, "nf", {}, None)
        w.urllib.request.urlopen = raise_404
        try:
            self.assertEqual(w.probe(), (True, "HTTP 404"))
        finally:
            w.urllib.request.urlopen = orig


if __name__ == "__main__":
    unittest.main()
