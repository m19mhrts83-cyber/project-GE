#!/usr/bin/env python3
"""WeStudy ログイン確認（共通 .env + Playwright）。"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from auth import load_westudy_env, westudy_login_url  # noqa: E402


def login_and_verify(*, show: bool) -> dict[str, str]:
    from playwright.sync_api import sync_playwright

    user = os.environ["WESTUDY_USER"]
    password = os.environ["WESTUDY_PASS"]
    login_url = westudy_login_url()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not show)
        page = browser.new_page()
        page.goto(login_url, wait_until="domcontentloaded", timeout=120_000)

        if page.locator("#user_login").count():
            page.fill("#user_login", user)
            page.fill("#user_pass", password)
            try:
                if page.locator("#rememberme").is_visible():
                    page.check("#rememberme")
            except Exception:
                pass
            page.click("#wp-submit")
            page.wait_for_load_state("networkidle", timeout=90_000)
            time.sleep(1.0)

        url = page.url
        title = page.title()
        cookies = [
            c["name"]
            for c in page.context.cookies()
            if "wordpress" in (c.get("name") or "").lower()
        ]

        for sel in ("#login_error", "#login_error_msg"):
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                err = (loc.first.inner_text() or "").strip()[:500]
                browser.close()
                raise RuntimeError(f"ログイン失敗: {err or url}")

        if url.rstrip("/").endswith("/login") or "wp-login.php" in url.lower():
            browser.close()
            raise RuntimeError(f"ログインに失敗しました: {url}")

        page.goto("https://westudy.co.jp/", wait_until="domcontentloaded")
        home_title = page.title()
        if show:
            print("--show: ブラウザは開いたままです。確認後に閉じてください。")
            time.sleep(3600)
        browser.close()

    return {
        "url": url,
        "title": title,
        "home_title": home_title,
        "wp_cookies": ", ".join(sorted(set(cookies))) or "（なし）",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="WeStudy ログイン確認")
    parser.add_argument("--show", action="store_true", help="ブラウザを表示")
    args = parser.parse_args()

    env_path = load_westudy_env(force=True)
    print(f"📎 認証: {env_path}")
    print(f"🔐 URL: {westudy_login_url()}")

    result = login_and_verify(show=args.show)
    print("✅ ログイン成功")
    print(f"   タイトル: {result['title']}")
    print(f"   URL: {result['url']}")
    print(f"   トップ: {result['home_title']}")
    print(f"   WordPressクッキー: {result['wp_cookies']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
