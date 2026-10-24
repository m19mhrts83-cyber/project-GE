#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""314 週次機械チェック（cron 遅延計算・エラー行判定）の単体テスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_weekly_review_314 as wr  # noqa: E402


class CronTests(unittest.TestCase):
    def test_weekday_noon(self):
        # 12:30 JST 平日 = 03:30 UTC 月〜金。2026-10-23 は金曜
        self.assertTrue(wr.cron_matches("30 3 * * 1-5", datetime(2026, 10, 23, 3, 30)))
        self.assertFalse(wr.cron_matches("30 3 * * 1-5", datetime(2026, 10, 24, 3, 30)))

    def test_step_and_list(self):
        self.assertTrue(wr.cron_matches("*/5 * * * *", datetime(2026, 10, 23, 1, 55)))
        self.assertTrue(wr.cron_matches("7,22 0-14,21-23 * * *", datetime(2026, 10, 23, 22, 22)))
        self.assertFalse(wr.cron_matches("7,22 0-14,21-23 * * *", datetime(2026, 10, 23, 16, 7)))

    def test_delay(self):
        created = datetime(2026, 10, 23, 8, 46, 57, tzinfo=timezone.utc)
        d = wr.schedule_delay_min(["30 3 * * 1-5"], created)
        self.assertAlmostEqual(d, 316.95, places=1)


class ErrorLineTests(unittest.TestCase):
    def _is_err(self, ln: str) -> bool:
        return bool(wr.ERROR_RE.search(wr.ZERO_COUNT_RE.sub("", ln)))

    def test_zero_counts_are_not_errors(self):
        self.assertFalse(self._is_err("- failed: なし"))
        self.assertFalse(self._is_err("# cursor ask done=3 failed=0 scanned=10"))
        self.assertFalse(self._is_err("- inbox 処理: 2件（追記 1 / failed 0）"))

    def test_real_errors(self):
        self.assertTrue(self._is_err("# #report history 失敗: not_in_channel"))
        self.assertTrue(self._is_err("RuntimeError: ZAIM_PASSWORD が未設定です"))
        self.assertTrue(self._is_err("# cursor ask done=3 failed=2 scanned=10"))


class CountErrorsTests(unittest.TestCase):
    def test_old_section_is_skipped(self):
        since = wr.datetime(2026, 10, 17, tzinfo=wr.JST)
        text = "\n".join([
            "[2026/10/12 21:13:43] ERROR    [MODEL][GATE] old",
            "RuntimeError: 古い節の続き",
            "======== 2026-10-24 08:03:11 ========",
            "FileNotFoundError: 下書きがありません",
        ])
        c = wr.count_errors(text, since)
        self.assertEqual(sum(c.values()), 1)

    def test_no_timestamp_counts_all(self):
        since = wr.datetime(2026, 10, 17, tzinfo=wr.JST)
        c = wr.count_errors("RuntimeError: a\nRuntimeError: a\n", since)
        self.assertEqual(sum(c.values()), 2)


if __name__ == "__main__":
    unittest.main()
