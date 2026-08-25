#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raimo CSV取込: CI の Target crashed を取込失敗にしないガード。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

# upload_csv_to_raimo は playwright 必須。未インストール環境でも判定関数だけ検証する。
_pw = MagicMock()
sys.modules.setdefault("playwright", _pw)
sys.modules.setdefault("playwright.sync_api", _pw.sync_api)
_pw.sync_api.Error = type("Error", (Exception,), {})
_pw.sync_api.TimeoutError = type("TimeoutError", (Exception,), {})
_pw.sync_api.sync_playwright = MagicMock()

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import upload_csv_to_raimo as u  # noqa: E402


class TestPageCrashDetect(unittest.TestCase):
    def test_screenshot_target_crashed_from_run_32625889438(self) -> None:
        exc = Exception(
            "Page.screenshot: Target crashed\nCall log:\n  - taking page screenshot"
        )
        self.assertTrue(u._is_page_crash_error(exc))

    def test_plain_page_crashed(self) -> None:
        self.assertTrue(u._is_page_crash_error(Exception("Page crashed")))


class TestSafeScreenshot(unittest.TestCase):
    def test_target_crashed_is_non_fatal(self) -> None:
        class BoomPage:
            def is_closed(self) -> bool:
                return False

            def screenshot(self, **kwargs):
                raise Exception("Page.screenshot: Target crashed")

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ok.png"
            self.assertFalse(u._safe_screenshot(BoomPage(), path, full_page=True))

    def test_closed_page_skips(self) -> None:
        page = SimpleNamespace(is_closed=lambda: True)
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(u._safe_screenshot(page, Path(td) / "x.png"))

    def test_none_page_skips(self) -> None:
        self.assertFalse(u._safe_screenshot(None, Path("x.png")))


class TestCiScreenshotSkip(unittest.TestCase):
    def setUp(self) -> None:
        self._old = {
            k: os.environ.get(k)
            for k in ("CI", "GITHUB_ACTIONS", "RAIMO_SCREENSHOT_IN_CI")
        }

    def tearDown(self) -> None:
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_github_actions_skips_success_shot(self) -> None:
        os.environ["GITHUB_ACTIONS"] = "true"
        os.environ.pop("RAIMO_SCREENSHOT_IN_CI", None)
        self.assertTrue(u._in_ci())
        self.assertFalse(u._should_take_success_screenshot())

    def test_override_allows_ci_shot(self) -> None:
        os.environ["GITHUB_ACTIONS"] = "true"
        os.environ["RAIMO_SCREENSHOT_IN_CI"] = "1"
        self.assertTrue(u._should_take_success_screenshot())


class TestCommunityRefreshSkip(unittest.TestCase):
    def test_env_zero_skips(self) -> None:
        old = os.environ.get("RAIMO_TRY_COMMUNITY_REFRESH")
        os.environ["RAIMO_TRY_COMMUNITY_REFRESH"] = "0"
        try:
            ok, msg = u.try_community_info_refresh(SimpleNamespace(frames=[]), 30)
            self.assertFalse(ok)
            self.assertIn("スキップ", msg)
        finally:
            if old is None:
                os.environ.pop("RAIMO_TRY_COMMUNITY_REFRESH", None)
            else:
                os.environ["RAIMO_TRY_COMMUNITY_REFRESH"] = old


if __name__ == "__main__":
    unittest.main()
