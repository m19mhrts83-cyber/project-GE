#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeStudy 週次 CI のログイン／フォーラム到達ガード（Selenium 不要）。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# westudy_forum_all は selenium 必須。未インストール環境でも判定関数だけ検証する。
for name in (
    "selenium",
    "selenium.webdriver",
    "selenium.webdriver.chrome",
    "selenium.webdriver.chrome.options",
    "selenium.webdriver.chrome.service",
    "selenium.webdriver.common",
    "selenium.webdriver.common.by",
    "selenium.webdriver.common.keys",
    "selenium.common",
    "selenium.common.exceptions",
    "selenium.webdriver.support",
    "selenium.webdriver.support.ui",
    "selenium.webdriver.support.expected_conditions",
):
    sys.modules.setdefault(name, MagicMock())

sys.path.insert(0, str(Path(__file__).resolve().parent))
import westudy_chrome as chrome  # noqa: E402
import westudy_forum_all as w  # noqa: E402


class TestCiChromePin(unittest.TestCase):
    def setUp(self):
        self._saved = {
            key: os.environ.get(key) for key in ("GITHUB_ACTIONS", "WESTUDY_CHROME_VERSION")
        }

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_not_pinned_outside_gha(self):
        os.environ.pop("GITHUB_ACTIONS", None)
        os.environ.pop("WESTUDY_CHROME_VERSION", None)
        self.assertIsNone(chrome.ci_chrome_browser_version())

    def test_default_pin_on_gha(self):
        os.environ["GITHUB_ACTIONS"] = "true"
        os.environ.pop("WESTUDY_CHROME_VERSION", None)
        self.assertEqual(chrome.ci_chrome_browser_version(), "153")

    def test_override(self):
        os.environ["GITHUB_ACTIONS"] = "true"
        os.environ["WESTUDY_CHROME_VERSION"] = "154"
        self.assertEqual(chrome.ci_chrome_browser_version(), "154")

    def test_stable_disables_pin(self):
        os.environ["GITHUB_ACTIONS"] = "true"
        os.environ["WESTUDY_CHROME_VERSION"] = "stable"
        self.assertIsNone(chrome.ci_chrome_browser_version())


class TestPartialLoadUsable(unittest.TestCase):
    def test_complete_with_form_is_usable(self):
        self.assertTrue(w._partial_load_usable("complete", 200, True))

    def test_complete_but_empty_is_not_usable(self):
        # run 31910341516: readyState=complete でも本文が空なら続行しない
        self.assertFalse(w._partial_load_usable("complete", 0, False))
        self.assertFalse(w._partial_load_usable("complete", 10, True))

    def test_missing_required_selector_is_not_usable(self):
        self.assertFalse(w._partial_load_usable("complete", 400, False))

    def test_loading_ready_state_is_not_usable(self):
        self.assertFalse(w._partial_load_usable("loading", 400, True))


class TestForumWaitAbort(unittest.TestCase):
    def test_forum_links_ready(self):
        self.assertIsNone(
            w._forum_wait_abort_reason(
                forum_links=3,
                guest_login=False,
                body_len=0,
                guest_hits=5,
                empty_hits=5,
            )
        )

    def test_guest_ui_fail_fast(self):
        reason = w._forum_wait_abort_reason(
            forum_links=0,
            guest_login=True,
            body_len=200,
            guest_hits=5,
            empty_hits=0,
        )
        self.assertEqual(reason, "未ログイン画面のまま")

    def test_empty_page_fail_fast(self):
        # ゲスト UI も無く本文も空 → 120秒待たずに打ち切る
        reason = w._forum_wait_abort_reason(
            forum_links=0,
            guest_login=False,
            body_len=0,
            guest_hits=0,
            empty_hits=5,
        )
        self.assertEqual(reason, "空ページのまま")

    def test_empty_page_needs_consecutive_hits(self):
        self.assertIsNone(
            w._forum_wait_abort_reason(
                forum_links=0,
                guest_login=False,
                body_len=0,
                guest_hits=0,
                empty_hits=4,
            )
        )

    def test_hydrating_shell_is_not_empty(self):
        self.assertIsNone(
            w._forum_wait_abort_reason(
                forum_links=0,
                guest_login=False,
                body_len=200,
                guest_hits=0,
                empty_hits=5,
            )
        )


if __name__ == "__main__":
    unittest.main()
