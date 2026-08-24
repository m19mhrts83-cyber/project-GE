#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""upload_csv_to_raimo: 取込成功後の Target crashed をジョブ失敗にしない。"""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

# playwright 未導入でもヘルパーを検証できるようスタブする
if "playwright.sync_api" not in sys.modules:
    pw = types.ModuleType("playwright")
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.Error = Exception
    sync_api.TimeoutError = type("TimeoutError", (Exception,), {})
    sync_api.sync_playwright = lambda: None
    sys.modules.setdefault("playwright", pw)
    sys.modules["playwright.sync_api"] = sync_api

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from upload_csv_to_raimo import _is_page_crash_error, _safe_screenshot  # noqa: E402


def test_is_page_crash_error_matches_gha_screenshot_crash() -> None:
    gha_msg = (
        "Page.screenshot: Target crashed \n"
        "Call log:\n"
        "  - taking page screenshot\n"
        "  - waiting for fonts to load...\n"
        "  - fonts loaded\n"
    )
    assert _is_page_crash_error(Exception(gha_msg))
    assert _is_page_crash_error(Exception("Page crashed"))
    assert _is_page_crash_error(Exception("Target closed"))
    assert not _is_page_crash_error(
        Exception("CSV取込の完了待ちがタイムアウトしました（1800秒）")
    )


class _CrashPage:
    def screenshot(self, **kwargs):
        raise RuntimeError("Page.screenshot: Target crashed")

    def content(self):
        raise RuntimeError("Target closed")


class _OkPage:
    def screenshot(self, path, full_page=False, timeout=15000):
        assert full_page is False
        Path(path).write_bytes(b"png")

    def content(self):
        return "<html></html>"


def test_safe_screenshot_does_not_raise_on_target_crashed() -> None:
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "raimo_import_ok.png"
        assert _safe_screenshot(_CrashPage(), dest) is False
        assert not dest.exists()


def test_safe_screenshot_writes_viewport_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "raimo_import_ok.png"
        assert _safe_screenshot(_OkPage(), dest) is True
        assert dest.is_file()
        assert dest.read_bytes() == b"png"


if __name__ == "__main__":
    test_is_page_crash_error_matches_gha_screenshot_crash()
    test_safe_screenshot_does_not_raise_on_target_crashed()
    test_safe_screenshot_writes_viewport_file()
    print("OK")
