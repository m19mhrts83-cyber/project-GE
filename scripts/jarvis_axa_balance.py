#!/usr/bin/env python3
"""アクサ生命 MyAXA から積立金／払いもどし金を取得（Mac・Playwright）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_axa_balance.py --headless --json

OTP 画面が出たら対話なしで失敗終了（週次はスキップ扱い）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://myweb.axa.co.jp/login"
ACCOUNT_VALUE_URL = "https://myweb.axa.co.jp/fund-allocation/account-value"
DEBUG_DIR = Path.home() / "Library" / "Logs" / "jarvis_portfolio" / "debug"

OTP_HINTS = ("認証コード", "ワンタイム", "確認コード", "2段階", "二段階", "SMS")
VALUE_LABELS = ("積立金", "払いもどし", "払戻", "評価額", "特別勘定")


@dataclass
class AxaResult:
    value_jpy: int
    value_text: str
    source_url: str
    parser_mode: str


def _yen_near_labels(text: str) -> tuple[int | None, str]:
    norm = (text or "").replace("\u3000", " ").replace(",", "")
    for label in VALUE_LABELS:
        m = re.search(
            rf"{re.escape(label)}[^0-9]{{0,40}}(\d{{4,12}})\s*円",
            norm,
        )
        if m:
            return int(m.group(1)), f"label:{label}"
    return None, ""


def fetch_axa_balance(*, headless: bool, timeout_ms: int, save_debug: bool) -> AxaResult:
    user = (os.environ.get("AXA_MYAXA_ID") or "").strip()
    password = (os.environ.get("AXA_MYAXA_PASSWORD") or "").strip()
    if not user or not password:
        raise RuntimeError("AXA_MYAXA_ID / AXA_MYAXA_PASSWORD が未設定です")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_context(locale="ja-JP").new_page()
        page.set_default_timeout(timeout_ms)
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        for name in ("はい", "閉じる"):
            btn = page.get_by_role("button", name=name)
            if btn.count() > 0:
                try:
                    btn.first.click(timeout=2000)
                    page.wait_for_timeout(800)
                except Exception:
                    pass
            txt = page.get_by_text(name, exact=True)
            if txt.count() > 0:
                try:
                    txt.first.click(timeout=2000)
                    page.wait_for_timeout(800)
                except Exception:
                    pass

        email = page.locator(
            "input[type='email'], input[name*='mail' i], input[id*='mail' i], "
            "input[name*='login' i], input[autocomplete='username']"
        ).first
        pw = page.locator("input[type='password']").first
        email.wait_for(state="visible", timeout=timeout_ms)
        email.fill(user)
        pw.fill(password)
        submit = page.locator("button[type='submit'], input[type='submit']").first
        submit.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)

        body = page.inner_text("body")
        if any(h in body for h in OTP_HINTS):
            raise RuntimeError("MyAXA が OTP を要求したため自動取得を止めました")

        try:
            page.goto(ACCOUNT_VALUE_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            pass

        text = page.inner_text("body")
        value, mode = _yen_near_labels(text)
        if value is None:
            if save_debug:
                DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                (DEBUG_DIR / "axa_last_page.html").write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(DEBUG_DIR / "axa_last_page.png"), full_page=True)
            raise RuntimeError("積立金／払いもどし金を抽出できませんでした")

        result = AxaResult(
            value_jpy=value,
            value_text=f"{value:,}円",
            source_url=page.url,
            parser_mode=mode,
        )
        browser.close()
        return result


def main() -> int:
    ap = argparse.ArgumentParser(description="MyAXA 積立金取得")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--timeout-ms", type=int, default=45000)
    ap.add_argument("--save-debug", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        result = fetch_axa_balance(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
        )
    except Exception as exc:
        print(f"取得失敗: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False))
    else:
        print(f"アクサ生命 積立金目安: {result.value_text} ({result.parser_mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
