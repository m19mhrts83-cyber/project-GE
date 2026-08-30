#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raimo CSV 取込の CI ガード（Playwright 不要）。"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

for name in (
    "playwright",
    "playwright.sync_api",
):
    sys.modules.setdefault(name, MagicMock())

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upload_csv_to_raimo as u  # noqa: E402


class TestPageCrashDetection(unittest.TestCase):
    def test_target_crashed_screenshot(self):
        # run 32625889438: 取込後 full_page screenshot
        exc = Exception("Page.screenshot: Target crashed")
        self.assertTrue(u._is_page_crash_error(exc))

    def test_page_crashed_wait(self):
        # run 31387928808: 取込待ち中
        exc = Exception("Page.wait_for_timeout: Page crashed")
        self.assertTrue(u._is_page_crash_error(exc))

    def test_unrelated_error_is_not_crash(self):
        self.assertFalse(u._is_page_crash_error(Exception("Timeout 30000ms exceeded")))


class TestCsvChunking(unittest.TestCase):
    def test_small_file_is_not_split(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "delta.csv"
            dest = Path(td) / "chunks"
            src.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
            out = u.split_csv_into_chunks(src, 80, dest)
            self.assertEqual(out, [src])

    def test_split_preserves_multiline_fields(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "delta.csv"
            dest = Path(td) / "chunks"
            with src.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["id", "content"])
                for i in range(5):
                    w.writerow([str(i), f"line1-{i}\nline2-{i}"])
            out = u.split_csv_into_chunks(src, 2, dest)
            self.assertEqual(len(out), 3)
            counts = []
            for p in out:
                with p.open(newline="", encoding="utf-8") as f:
                    rows = list(csv.reader(f))
                self.assertEqual(rows[0], ["id", "content"])
                counts.append(len(rows) - 1)
                self.assertIn("\n", rows[1][1])
            self.assertEqual(counts, [2, 2, 1])

    def test_zero_max_rows_disables_split(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "delta.csv"
            src.write_text("a,b\n1,2\n3,4\n5,6\n", encoding="utf-8")
            out = u.split_csv_into_chunks(src, 0, Path(td) / "chunks")
            self.assertEqual(out, [src])


class TestStatsMerge(unittest.TestCase):
    def test_merge(self):
        total = {"ok": 0, "skip": 0, "ng": 0}
        u._merge_import_stats(total, {"ok": 10, "skip": 2, "ng": 1})
        u._merge_import_stats(total, {"ok": 3, "skip": 0, "ng": 0})
        self.assertEqual(total, {"ok": 13, "skip": 2, "ng": 1})


if __name__ == "__main__":
    unittest.main()
