#!/usr/bin/env python3
"""Finto カード後払い — クレジットカード登録画面まで（Chrome CDP）。

  ~/git-repos/scripts/jarvis_finto_card_register.py
  ~/git-repos/scripts/jarvis_finto_card_register.py --open   # サインインURLのみ

.env.jarvis_private:
  FINTO_USER / FINTO_PASSWORD
  OLIVE_FLEXIBLE_PAY_CREDIT_* （6777 登録用。CID/CVC は画面で手入力推奨）
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.chrome_cdp import cdp_ready, open_in_chrome, start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402

CDP_PORT = 9227
PROFILE = Path.home() / ".jarvis_state" / "chrome_finto"
SIGNIN = "https://user.finto.jp/signin"


def _is_maintenance(page: Page) -> bool:
    body = page.inner_text("body")
    return "メンテナンス" in body or page.title().lower() == "maintenance"


def _login(page: Page, user: str, password: str) -> None:
    page.goto(SIGNIN, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1500)
    if _is_maintenance(page):
        raise RuntimeError(
            "Finto はメンテナンス中です（表示: 22:00〜05:00）。終了後に再実行してください。"
        )
    # Cognito へ遷移する「ログイン」ボタンがある場合は先に押す
    if page.locator("input[type='password']").count() == 0:
        for sel in [
            "button:has-text('ログイン')",
            "a:has-text('ログイン')",
            "button:has-text('サインイン')",
        ]:
            btn = page.locator(sel)
            if btn.count() and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(2500)
                break
    page.wait_for_selector("input[type='password']", timeout=30000)
    for sel in [
        "input[name='username']",
        "input#signInFormUsername",
        "input[type='email']",
        "input[type='text']",
    ]:
        loc = page.locator(sel)
        if loc.count() and loc.first.is_visible():
            loc.first.fill(user)
            break
    page.locator("input[type='password']").first.fill(password)
    for sel in ["button:has-text('サインイン')", "input[type='submit']", "button[type='submit']"]:
        btn = page.locator(sel)
        if btn.count() and btn.first.is_visible():
            btn.first.click()
            break
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    if _is_maintenance(page):
        raise RuntimeError("ログイン後もメンテナンス画面のままです。")


def _dump_nav(page: Page) -> None:
    print(f"📎 URL: {page.url}")
    for kw in ["設定", "クレジット", "カード", "請求一覧", "ホーム"]:
        if kw in page.inner_text("body"):
            print(f"   本文に「{kw}」あり")
    links = page.eval_on_selector_all(
        "a, button",
        """els => els.map(e => ({
            tag: e.tagName,
            text: (e.innerText || e.value || '').trim().slice(0, 60),
            href: e.href || '',
            visible: !!(e.offsetWidth || e.offsetHeight)
        })).filter(x => x.visible && /設定|カード|クレジット|請求|ホーム|追加|変更|登録/.test(x.text))""",
    )
    for a in links[:30]:
        print("  NAV:", a)


def _try_open_card_settings(page: Page) -> None:
    """設定・カード管理っぽいリンクを順に試す。"""
    patterns = [
        r"クレジットカード",
        r"カード情報",
        r"カード管理",
        r"支払.*カード",
        r"設定",
    ]
    for pat in patterns:
        loc = page.get_by_role("link", name=re.compile(pat))
        if loc.count() and loc.first.is_visible():
            print(f"📎 クリック: {pat}")
            loc.first.click()
            page.wait_for_timeout(3000)
            _dump_nav(page)
            return
    _dump_nav(page)


def run(wait_sec: int, port: int) -> int:
    env = load_env(ENV_FILE)
    user = env.get("FINTO_USER", "")
    pw = env.get("FINTO_PASSWORD", "")
    last4 = env.get("OLIVE_FLEXIBLE_PAY_CREDIT_LAST4", "6777")

    if not user or not pw:
        print(
            "FINTO_USER / FINTO_PASSWORD が未設定です。"
            " .env.jarvis_private に追記後「保存した」と一声ください。",
            file=sys.stderr,
        )
        return 1

    start_cdp_chrome(port, PROFILE, SIGNIN)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        print("📎 Finto ログイン…")
        _login(page, user, pw)
        print("📎 ログイン後メニュー探索…")
        _try_open_card_settings(page)
        print("")
        print("=" * 60)
        print(f"✅ Chrome — Finto ログイン済み（port {port}）")
        print(f"   Olive Infinite（下4桁 {last4}）を登録する場合:")
        print("   1. 左メニュー「設定」等 → クレジットカード → 新規登録")
        print("   2. または「請求一覧」→ 支払予定行 → カード後払い申請時にカード選択")
        print("   ※ Olive はナンバーレス。番号は Vpass アプリで確認")
        print("   ※ CVC・3Dセキュアは手入力")
        print(f"   この Chrome は {wait_sec} 秒間開いたままです")
        print("=" * 60)
        time.sleep(wait_sec)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Finto カード登録補助（Chrome）")
    parser.add_argument("--open", action="store_true", help="サインインURLのみ開く")
    parser.add_argument("--port", type=int, default=CDP_PORT)
    parser.add_argument("--wait-sec", type=int, default=600)
    args = parser.parse_args()
    if args.open:
        open_in_chrome(SIGNIN)
        print("📎 メンテナンス中の場合は 05:00 以降に再試行してください")
        return 0
    if not cdp_ready(args.port):
        pass
    try:
        return run(args.wait_sec, args.port)
    except (PlaywrightTimeout, TimeoutError, RuntimeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
