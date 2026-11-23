"""111 夜枠 #report: 失敗がある晩だけ見出しに ⚠️ が付くこと。"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_partner_slack_report as r  # noqa: E402


def _args(failures: str) -> argparse.Namespace:
    return argparse.Namespace(
        frame="night", gmail=1, chatwork=0, line=0, other=0,
        failures=failures, note="", next="",
    )


class FailMarkTest(unittest.TestCase):
    def test_fail_has_warning_on_first_line(self) -> None:
        text = r._build_text(_args("line sync失敗（直近補完のみ）"), 1)
        self.assertTrue(text.splitlines()[0].startswith("⚠️【"))
        self.assertIn("・失敗:", text)

    def test_no_fail_unchanged(self) -> None:
        text = r._build_text(_args("なし"), 1)
        self.assertNotIn("⚠️", text)
        self.assertTrue(text.startswith("【"))


if __name__ == "__main__":
    unittest.main()
