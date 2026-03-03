#!/usr/bin/env python3
"""東海労金ログイン後のページ構造を確認するデバッグスクリプト。"""
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv
load_dotenv(SCRIPT_DIR.parent.parent / ".env")
load_dotenv(SCRIPT_DIR / ".env")

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.parasol.anser.ne.jp/ib/index.do?PT=BS&CCT0080=2972"
OUTPUT_HTML = SCRIPT_DIR / "debug_after_login.html"
OUTPUT_SCREENSHOT = SCRIPT_DIR / "debug_after_login.png"

def main():
    user = os.environ.get("TOKAIROKIN_USER") or os.environ.get("TOKAIROKIN_ID")
    password = os.environ.get("TOKAIROKIN_PASS") or os.environ.get("TOKAIROKIN_PASSWORD")
    if not user or not password:
        print("TOKAIROKIN_USER と TOKAIROKIN_PASS を .env に設定してください。")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            print("ログイン中...")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(2000)

            page.locator("#txtBox005").fill(user)
            page.locator("#pswd010").fill(password)
            page.locator("#btn012").first.click()

            page.wait_for_timeout(5000)

            # ワンタイムパスワード入力画面の可能性
            body = page.locator("body").inner_text()
            if "ワンタイム" in body or "追加認証" in body:
                print("※ ワンタイムパスワード入力画面の可能性。10秒待機...")
                page.wait_for_timeout(10000)

            OUTPUT_HTML.write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(OUTPUT_SCREENSHOT))
            print(f"HTML: {OUTPUT_HTML}")
            print(f"スクリーンショット: {OUTPUT_SCREENSHOT}")

            # 振込関連のリンク・ボタンを列挙
            keywords = ["振込", "振替", "振り込み"]
            for kw in keywords:
                links = page.locator(f"a:has-text('{kw}'), button:has-text('{kw}'), input[value*='{kw}']").all()
                if links:
                    print(f"\n--- '{kw}' を含む要素: {len(links)}件 ---")
                    for i, el in enumerate(links[:10]):
                        try:
                            tag = el.evaluate("el => el.tagName")
                            text = el.inner_text()[:50] if tag != "INPUT" else el.get_attribute("value") or ""
                            href = el.get_attribute("href") or ""
                            print(f"  [{i}] {tag} text={text!r} href={href[:60] if href else ''}")
                        except Exception as e:
                            print(f"  [{i}] 取得失敗: {e}")

            print("\n15秒待機（画面確認用）...")
            page.wait_for_timeout(15000)

        finally:
            browser.close()

if __name__ == "__main__":
    main()
