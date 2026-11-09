import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jarvis_mail_action_unseen as u  # noqa: E402
import jarvis_mail_action_slack_post as ma  # noqa: E402

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)  # 21:00 JST


def row(**pl):
    return {"id": "gha-abc123", "status": "pending", "subject": "件名", "from_email": "a@x.jp", "payload": pl}


class UnseenTest(unittest.TestCase):
    def test_posted_and_untouched_is_due(self):
        self.assertTrue(u.is_unseen_due(row(slack_ma_posted_at="2026-11-09T12:34:40+0900"), now=NOW))

    def test_too_fresh_or_acted_or_not_posted(self):
        self.assertFalse(u.is_unseen_due(row(slack_ma_posted_at="2026-11-09T19:00:00+0900"), now=NOW))
        self.assertFalse(u.is_unseen_due(row(slack_ma_posted_at="2026-11-09T07:00:00+0900", slack_ma_action={"action": "skip"}), now=NOW))
        self.assertFalse(u.is_unseen_due(row(), now=NOW))
        self.assertFalse(u.is_unseen_due({**row(slack_ma_posted_at="2026-11-09T07:00:00+0900"), "status": "sent"}, now=NOW))
        self.assertFalse(u.is_unseen_due(row(slack_ma_posted_at="2026-11-09T07:00:00+0900", slack_ma_dedupe_sibling_of="x"), now=NOW))

    def test_counted_once_per_post(self):
        pl = {"slack_ma_posted_at": "2026-11-09T07:00:00+0900"}
        stamped = u.stamp_unseen(pl, now=NOW)
        self.assertEqual(stamped["slack_ma_unseen_count"], 1)
        self.assertFalse(u.is_unseen_due(row(**stamped), now=NOW))
        # 翌日に出し直したら、その回はもう一度数える
        again = {**stamped, "slack_ma_posted_at": "2026-11-10T07:00:00+0900"}
        self.assertTrue(u.is_unseen_due(row(**again), now=datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)))

    def test_record_shape(self):
        rec = u.unseen_record(row(slack_ma_posted_at="2026-11-09T12:00:00+0900", slack_ma_digest={"score": 42}), now=NOW)
        self.assertEqual(rec["action"], "unseen")
        self.assertEqual(rec["surface"], "triage")
        self.assertEqual(rec["payload"]["ai_rank"], 42)
        self.assertEqual(rec["payload"]["hours_since_post"], 9.0)
        self.assertIn("unseen:2026-11-09T12:00:00+0900", rec["idem_key"])


class NearMissTest(unittest.TestCase):
    def test_stamp_only_unposted(self):
        out = ma.near_miss_stamp({}, score=30, reasons=["partner"], rank=6, at="t")
        self.assertEqual(out["slack_ma_near_miss"]["rank"], 6)
        self.assertIsNone(ma.near_miss_stamp({"slack_ma_posted_at": "x"}, score=1, reasons=[], rank=6, at="t"))
        self.assertIsNone(ma.near_miss_stamp(out, score=1, reasons=[], rank=7, at="t"))

    def test_env(self):
        os.environ["JARVIS_MAIL_ACTION_NEAR_MISS"] = "0"
        try:
            self.assertEqual(ma.near_miss_n(), 0)
        finally:
            del os.environ["JARVIS_MAIL_ACTION_NEAR_MISS"]
        self.assertEqual(ma.near_miss_n(), 3)


if __name__ == "__main__":
    unittest.main()
