#!/usr/bin/env python3
"""SBI証券の口座評価額を取得（Mac・Playwright）。インデックス枠の週次用。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_sbi_index_balance.py --headless --json

発注はしない。OTP が出たら失敗終了。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.sbisec.co.jp/ETGate"
DEBUG_DIR = Path.home() / "Library" / "Logs" / "jarvis_portfolio" / "debug"
OTP_HINTS = ("認証番号", "ワンタイム", "確認コード", "デバイス認証", "追加認証")
VALUE_LABELS = ("評価額合計", "時価評価額", "評価額", "合計資産")


@dataclass
class SbiResult:
    value_jpy: int
    value_text: str
    source_url: str
    parser_mode: str


def _yen_near_labels(text: str) -> tuple[int | None, str]:
    norm = (text or "").replace("\u3000", " ")
    for label in VALUE_LABELS:
        m = re.search(
            rf"{re.escape(label)}[^0-9]{{0,40}}([\d,]{{4,14}})\s*円",
            norm,
        )
        if m:
            return int(m.group(1).replace(",", "")), f"label:{label}"
    return None, ""


def fetch_sbi_balance(*, headless: bool, timeout_ms: int, save_debug: bool) -> SbiResult:
    user = (os.environ.get("SBI_SEC_USER") or "").strip()
    password = (os.environ.get("SBI_SEC_LOGIN_PASSWORD") or "").strip()
    if not user or not password:
        raise RuntimeError("SBI_SEC_USER / SBI_SEC_LOGIN_PASSWORD が未設定です")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_context(locale="ja-JP").new_page()
        page.set_default_timeout(timeout_ms)
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        uid_sel = (
            "input[name='user_id'], input#user_id, input[name='username'], "
            "input[id*='user_id'], input[placeholder*='ユーザー']"
        )
        pw_sel = "input[name='user_password'], input[type='password']"
        uid = page.locator(uid_sel).first
        pw = page.locator(pw_sel).first
        if uid.count() == 0:
            for frame in page.frames:
                if frame.locator(uid_sel).count() > 0:
                    uid = frame.locator(uid_sel).first
                    pw = frame.locator(pw_sel).first
                    break
        uid.wait_for(state="visible", timeout=timeout_ms)
        uid.fill(user)
        pw.fill(password)
        submit = page.locator(
            "input[name='ACT_login'], input[type='submit'], button[type='submit']"
        ).first
        if submit.count() == 0:
            for frame in page.frames:
                loc = frame.locator(
                    "input[name='ACT_login'], input[type='submit'], button[type='submit']"
                )
                if loc.count() > 0:
                    submit = loc.first
                    break
        submit.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)

        body = page.inner_text("body")
        if any(h in body for h in OTP_HINTS):
            raise RuntimeError("SBI が追加認証を要求したため自動取得を止めました")

        value, mode = _yen_near_labels(body)
        if value is None:
            for text in ("口座管理", "保有証券", "資産状況"):
                loc = page.locator(f"a:has-text('{text}')")
                if loc.count() > 0:
                    loc.first.click()
                    page.wait_for_timeout(2000)
                    body = page.inner_text("body")
                    value, mode = _yen_near_labels(body)
                    if value is not None:
                        break

        if value is None:
            if save_debug:
                DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                (DEBUG_DIR / "sbi_last_page.html").write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(DEBUG_DIR / "sbi_last_page.png"), full_page=True)
            raise RuntimeError("SBI の評価額を抽出できませんでした")

        result = SbiResult(
            value_jpy=value,
            value_text=f"{value:,}円",
            source_url=page.url,
            parser_mode=mode,
        )
        browser.close()
        return result


def main() -> int:
    ap = argparse.ArgumentParser(description="SBI証券 評価額取得")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--timeout-ms", type=int, default=45000)
    ap.add_argument("--save-debug", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        result = fetch_sbi_balance(
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
        print(f"SBI 評価額: {result.value_text} ({result.parser_mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
