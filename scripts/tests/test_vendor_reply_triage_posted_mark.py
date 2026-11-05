"""業者返信の再取込で Slack 投稿済み印が消えない（重複投稿の再発防止 2026-11-05）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis_kurashift_vendor_reply_triage import merge_posted_marks  # noqa: E402


class MergePostedMarksTest(unittest.TestCase):
    def test_keeps_slack_marks(self) -> None:
        row = {"id": "re-vendor-x", "payload": {"re_vendor_reply": True}}
        merge_posted_marks(
            row,
            {"re_vendor_reply": True, "slack_vr_posted_at": "2026-11-04T05:04:48Z", "slack_ma_posted_at": "t"},
        )
        self.assertEqual(row["payload"]["slack_vr_posted_at"], "2026-11-04T05:04:48Z")
        self.assertEqual(row["payload"]["slack_ma_posted_at"], "t")

    def test_ignores_other_keys_and_none(self) -> None:
        row = {"id": "re-vendor-x", "payload": {"vendor_status": "replied"}}
        merge_posted_marks(row, {"vendor_status": "contacted", "foo": 1})
        self.assertEqual(row["payload"], {"vendor_status": "replied"})
        merge_posted_marks(row, None)
        self.assertEqual(row["payload"], {"vendor_status": "replied"})


if __name__ == "__main__":
    unittest.main()
