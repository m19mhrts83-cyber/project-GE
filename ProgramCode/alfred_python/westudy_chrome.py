#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeStudy スクレイパの CI Chrome 固定。

2026-10-04 の週次 (run 37171011849) は Selenium Manager が入れた
Chrome 154.0.8037.57 でログインナビゲーションが data:, のまま
renderer timeout（body_len=0）になり、全リトライが失敗した。
直前の成功週 (2026-09-27, run 36284508865) は 153 系。
GitHub Actions のときだけ major を固定する。ローカルはインストール済み Chrome のまま。
"""

from __future__ import annotations

import os

# 成功実績のある major。WESTUDY_CHROME_VERSION=stable で固定を外す。
DEFAULT_CI_CHROME_MAJOR = "153"


def ci_chrome_browser_version() -> str | None:
    """GitHub Actions で Selenium に渡す browser_version。ローカルは None。"""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return None
    pinned = (os.environ.get("WESTUDY_CHROME_VERSION") or DEFAULT_CI_CHROME_MAJOR).strip()
    if not pinned or pinned.lower() in {"stable", "latest", "0"}:
        return None
    return pinned


def apply_ci_chrome_pin(options) -> str | None:
    """options.browser_version を設定し、固定した版（または None）を返す。"""
    version = ci_chrome_browser_version()
    if version:
        options.browser_version = version
    return version
