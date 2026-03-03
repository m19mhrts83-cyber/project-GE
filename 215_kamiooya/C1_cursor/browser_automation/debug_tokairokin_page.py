#!/usr/bin/env python3
"""東海労金ログインページの構造を確認するデバッグスクリプト。"""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.parasol.anser.ne.jp/ib/index.do?PT=BS&CCT0080=2972"
OUTPUT_HTML = SCRIPT_DIR / "debug_tokairokin_parasol.html"
OUTPUT_SCREENSHOT = SCRIPT_DIR / "debug_tokairokin_parasol.png"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            print("ページにアクセス中...")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=25000)
            page.wait_for_timeout(3000)

            # HTMLを保存
            html = page.content()
            OUTPUT_HTML.write_text(html, encoding="utf-8")
            print(f"HTML保存: {OUTPUT_HTML}")

            # スクリーンショット
            page.screenshot(path=str(OUTPUT_SCREENSHOT))
            print(f"スクリーンショット: {OUTPUT_SCREENSHOT}")

            # 全input要素を列挙
            inputs = page.locator("input").all()
            print(f"\n--- input要素: {len(inputs)}件 ---")
            for i, inp in enumerate(inputs):
                try:
                    itype = inp.get_attribute("type") or "text"
                    name = inp.get_attribute("name") or ""
                    id_attr = inp.get_attribute("id") or ""
                    placeholder = inp.get_attribute("placeholder") or ""
                    print(f"  [{i}] type={itype} name={name!r} id={id_attr!r} placeholder={placeholder!r}")
                except Exception as e:
                    print(f"  [{i}] (取得失敗: {e})")

            # iframe内のinputも確認
            frames = page.frames
            print(f"\n--- フレーム数: {len(frames)} ---")
            for fi, frame in enumerate(frames):
                try:
                    inps = frame.locator("input").all()
                    if inps:
                        print(f"  フレーム[{fi}] URL={frame.url[:60]}... input={len(inps)}件")
                        for i, inp in enumerate(inps[:5]):
                            itype = inp.get_attribute("type") or "text"
                            name = inp.get_attribute("name") or ""
                            id_attr = inp.get_attribute("id") or ""
                            print(f"    input[{i}] type={itype} name={name!r} id={id_attr!r}")
                except Exception as e:
                    print(f"  フレーム[{fi}] エラー: {e}")

            print("\n5秒待機（画面確認用）...")
            page.wait_for_timeout(5000)

        finally:
            browser.close()

if __name__ == "__main__":
    main()
