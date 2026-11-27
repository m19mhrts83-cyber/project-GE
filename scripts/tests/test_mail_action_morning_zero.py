#!/usr/bin/env python3
"""朝0件の1行（架空の数字のみ・Slack送信なし）。"""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_mail_action_slack_post as ma  # noqa: E402


class MorningZeroTest(unittest.TestCase):
    def test_text(self):
        t = ma.morning_zero_line_text({"skim_skip": 12, "vendor_skip": 3})
        self.assertEqual(t, "🟢 116 要対応0件（流し読み12・業者返信3）")

    def test_text_missing_stats(self):
        self.assertIn("流し読み0・業者返信0", ma.morning_zero_line_text({}))

    def test_due_only_morning_zero(self):
        self.assertTrue(ma.morning_zero_line_due(morning=True, from_triage=True, posted=0, final_rows=0))

    def test_not_due_with_cards(self):
        self.assertFalse(ma.morning_zero_line_due(morning=True, from_triage=True, posted=0, final_rows=2))
        self.assertFalse(ma.morning_zero_line_due(morning=True, from_triage=True, posted=1, final_rows=0))

    def test_not_due_outside_morning(self):
        self.assertFalse(ma.morning_zero_line_due(morning=False, from_triage=True, posted=0, final_rows=0))

    def test_dry_run_prints_without_sending(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = ma.notify_morning_zero_line(None, {"skim_skip": 5, "vendor_skip": 1}, dry_run=True)
        self.assertTrue(ok)
        self.assertIn("要対応0件（流し読み5・業者返信1）", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
