#!/usr/bin/env python3
"""既存の NotebookLM ノートにソース（ファイル）を追加する。

新規ノート作成（jarvis_notebooklm_create_and_upload.py）は空ノートを増やすため、
既存ノートへ1ファイル足したいときはこちらを使う。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_notebooklm_add_source.py \
    --notebook-url 'https://notebooklm.google.com/notebook/<id>' \
    --file '/path/to/07_....md'

使用プロファイル: studio（admin でログイン済み）
失敗時は /tmp/notebooklm_add_source/ にスクリーンショットと DOM ダンプを残す。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

STUDIO_PROFILE = Path.home() / "Library/Application Support/notebooklm-studio/chrome_profile"
DEBUG = Path("/tmp/notebooklm_add_source")

ADD_SRC_SELECTORS = (
    "button:has-text('ソースを追加')",
    "button:has-text('Add source')",
    "[aria-label*='ソースを追加']",
    "[aria-label*='Add source']",
)
UPLOAD_SELECTORS = (
    "button:has-text('ファイルをアップロード')",
    "[aria-label*='ファイルをアップロード']",
    "button:has-text('Upload files')",
    "[aria-label*='Upload files']",
)


def dump_debug(page, tag: str) -> None:
    DEBUG.mkdir(parents=True, exist_ok=True)
    try:
        (DEBUG / f"{tag}.png").write_bytes(page.screenshot(full_page=True))
    except Exception:
        pass
    try:
        (DEBUG / f"{tag}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    # クリックできそうな要素の一覧（テキスト / aria-label）
    try:
        items = page.eval_on_selector_all(
            "button,[role=button],a",
            "els => els.map(e => (e.innerText||'').trim().slice(0,40) + ' :: ' + (e.getAttribute('aria-label')||''))",
        )
        (DEBUG / f"{tag}.buttons.txt").write_text("\n".join(items), encoding="utf-8")
        print(f"# 候補ボタン: {DEBUG / (tag + '.buttons.txt')}", file=sys.stderr)
    except Exception:
        pass
    print(f"# debug: {DEBUG}/{tag}.png / .html", file=sys.stderr)


def click_first(page, selectors) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=5000)
                return True
        except Exception:
            continue
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="既存 NotebookLM ノートへソース追加")
    ap.add_argument("--notebook-url", required=True)
    ap.add_argument("--file", required=True, help="追加するファイル（.md 等）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = Path(args.file).expanduser()
    if not src.is_file():
        print(f"# FAIL file not found: {src}", file=sys.stderr)
        return 2
    if not STUDIO_PROFILE.is_dir():
        print(f"# FAIL studio profile なし: {STUDIO_PROFILE}", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(STUDIO_PROFILE),
            headless=False,
            viewport={"width": 1400, "height": 950},
            locale="ja-JP",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(args.notebook_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        body = page.inner_text("body")
        if src.name in body:
            print(f"# すでに登録済み: {src.name}")
            ctx.close()
            return 0

        if not click_first(page, ADD_SRC_SELECTORS):
            dump_debug(page, "no_add_source_button")
            ctx.close()
            return 1
        page.wait_for_timeout(2000)

        if args.dry_run:
            print("# dry-run: 「ソースを追加」を開いたところで停止")
            dump_debug(page, "dry_run_modal")
            ctx.close()
            return 0

        # クリックで file chooser が開く
        try:
            with page.expect_file_chooser(timeout=10000) as fc:
                if not click_first(page, UPLOAD_SELECTORS):
                    raise RuntimeError("upload button not found")
            fc.value.set_files(str(src))
        except Exception as e:  # noqa: BLE001
            print(f"# file chooser 失敗 ({type(e).__name__}) → input[type=file] を試行", file=sys.stderr)
            try:
                page.set_input_files("input[type=file]", str(src), timeout=8000)
            except Exception:
                dump_debug(page, "no_file_input")
                ctx.close()
                return 1

        print(f"# アップロード開始: {src.name}")
        for _ in range(30):
            page.wait_for_timeout(2000)
            if src.name in page.inner_text("body"):
                print(f"# 登録確認OK: {src.name}")
                page.wait_for_timeout(3000)
                ctx.close()
                return 0
        dump_debug(page, "ingest_timeout")
        ctx.close()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
