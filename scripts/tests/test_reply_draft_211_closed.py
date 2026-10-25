# -*- coding: utf-8 -*-
"""211: クローズ済み案件（config/reply_draft_211_closed.json）を起案・相談から外す。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jarvis_reply_draft_211 as rd  # noqa: E402


class ClosedCaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "closed.json"
        self.path.write_text(
            json.dumps({"closed": [{"folder": "P103_Tcell", "through": "2026-10-23"}]}),
            encoding="utf-8",
        )
        self.patch = mock.patch.object(rd, "CLOSED_PATH", self.path)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.tmp.cleanup()

    def test_closed_through_inclusive(self) -> None:
        closed = rd._load_closed()
        self.assertTrue(rd._is_closed({"folder": "P103_Tcell", "received_at": "2026/10/23"}, closed))
        self.assertTrue(rd._is_closed({"folder": "P103_Tcell", "received_at": "2026/10/15"}, closed))
        self.assertFalse(rd._is_closed({"folder": "P103_Tcell", "received_at": "2026/10/24"}, closed))
        self.assertFalse(rd._is_closed({"folder": "P101_Other", "received_at": "2026/10/15"}, closed))

    def test_candidates_skip_closed(self) -> None:
        items = [
            {"lane": "partner", "folder": "P103_Tcell", "received_at": "2026/10/22",
             "subject": "(件名なし)", "summary": "退去 見積"},
        ]
        with mock.patch.object(rd, "_is_pm_folder", return_value=True):
            applyable, b_waiting, _ = rd._pm_candidates(items, lookback_days=36500)
        self.assertEqual(applyable, [])
        self.assertEqual(b_waiting, [])

    def test_missing_file_is_empty(self) -> None:
        self.path.unlink()
        self.assertEqual(rd._load_closed(), {})


class TemplateHintTest(unittest.TestCase):
    def test_line_summary_html_stripped(self) -> None:
        it = {
            "channel": "LINE",
            "summary": "<details> <summary>本文</summary> 2026/10/21 09:12 yuki 内容確認しました！ </details>",
        }
        out = rd._template_draft(it)
        self.assertNotIn("<details>", out)
        self.assertNotIn("本文", out)
        self.assertIn("「内容確認しました！」確認しました。", out)


if __name__ == "__main__":
    unittest.main()
