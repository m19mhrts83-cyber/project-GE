#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raimo 取込: 取込完了後の Target crashed で CI を落とさないこと。"""

from __future__ import annotations

import io
import sys
import tempfile
import types
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))


def _install_playwright_stub() -> None:
    """CI/クラウドでは playwright が無いので、import だけ通す stub を入れる。"""
    if "playwright.sync_api" in sys.modules:
        return
    pw = types.ModuleType("playwright")
    sync = types.ModuleType("playwright.sync_api")

    class Error(Exception):
        pass

    class TimeoutError(Error):
        pass

    def sync_playwright():  # pragma: no cover
        raise RuntimeError("playwright stub: sync_playwright は使わない")

    sync.Error = Error
    sync.TimeoutError = TimeoutError
    sync.sync_playwright = sync_playwright
    sys.modules.setdefault("playwright", pw)
    sys.modules["playwright.sync_api"] = sync


_install_playwright_stub()
import upload_csv_to_raimo as raimo  # noqa: E402


class _BoomPage:
    def screenshot(self, **_kwargs):
        raise RuntimeError("Page.screenshot: Target crashed")

    @property
    def frames(self):
        raise RuntimeError("Target crashed")


class _ToastFrame:
    def locator(self, _sel: str):
        raise RuntimeError("Target crashed")


def test_is_page_crash_error_matches_gha_log() -> None:
    err = RuntimeError("Page.screenshot: Target crashed")
    assert raimo._is_page_crash_error(err)
    assert raimo._is_page_crash_error(RuntimeError("Target closed"))
    assert not raimo._is_page_crash_error(RuntimeError("login failed"))


def test_safe_screenshot_does_not_raise() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ok.png"
        ok = raimo._safe_screenshot(_BoomPage(), path)
        assert ok is False
        assert not path.exists()


def test_all_page_like_survives_dead_frames() -> None:
    page = _BoomPage()
    out = raimo._all_page_like(page)
    assert out == [page]


def test_post_import_housekeeping_survives_target_crashed() -> None:
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        toast = raimo._post_import_housekeeping(
            _BoomPage(), _ToastFrame(), Path(tempfile.gettempdir())
        )
    finally:
        sys.stdout = old
    assert toast == ""
    assert "コミュニティ最新化" in buf.getvalue()


if __name__ == "__main__":
    test_is_page_crash_error_matches_gha_log()
    test_safe_screenshot_does_not_raise()
    test_all_page_like_survives_dead_frames()
    test_post_import_housekeeping_survives_target_crashed()
    print("OK")
