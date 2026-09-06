#!/usr/bin/env python3
"""
NotebookLM に新規ノートブックを作成し、指定した Google Drive フォルダ内のファイルを一括アップロードする自動化スクリプト。

使用アカウント: admin (NOTEBOOKLM_EMAIL / NOTEBOOKLM_PASSWORD)

使用例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_notebooklm_create_and_upload.py \
    --folder "09_家族受験会議2026秋_円香と珠己" \
    --title "家族受験会議2026秋（円香・珠己）"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_notebooklm_studio_lib import (  # noqa: E402
    expand,
    load_cfg,
)

DRIVE_ROOT = Path(
    os.path.expanduser(
        "~/Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp/マイドライブ/200_NoteBookLM"
    )
)
PROFILE_STUDIO = Path.home() / "Library/Application Support/notebooklm-studio/chrome_profile"


def login_if_needed(page, email: str, password: str) -> None:
    """必要に応じて Google アカウントにログインする。"""
    page.goto(
        "https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fnotebooklm.google.com%2F",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    page.wait_for_timeout(2000)

    # 既にログイン済みの場合はスキップ
    if "notebooklm.google.com" in page.url or "notebook.google.com" in page.url:
        print("# Already logged in to NotebookLM", file=sys.stderr)
        return

    # confirmidentifier または email input
    next_btn = page.locator("button:has-text('次へ')")
    if next_btn.count():
        try:
            next_btn.first.click(timeout=3000)
            page.wait_for_timeout(2000)
        except Exception:
            pass

    email_input = page.locator("input[type='email'], input[name='identifier'], #identifierId")
    if email_input.count() and email_input.first.is_visible():
        email_input.first.fill(email)
        if next_btn.count():
            next_btn.first.click(timeout=3000)
            page.wait_for_timeout(2000)

    # password input
    pw_input = page.locator("input[name='Passwd'], input[type='password']")
    if pw_input.count() and pw_input.first.is_visible():
        pw_input.first.fill(password)
        if next_btn.count():
            next_btn.first.click(timeout=3000)
            page.wait_for_timeout(5000)

    print(f"# Logged in! Current URL: {page.url}", file=sys.stderr)


def create_and_upload(
    folder_name: str,
    title: str | None = None,
    files: list[str] | None = None,
    headed: bool = False,
) -> dict:
    from playwright.sync_api import sync_playwright

    target_dir = DRIVE_ROOT / folder_name
    if not target_dir.is_dir():
        raise FileNotFoundError(f"Target folder not found: {target_dir}")

    # アップロード対象ファイルの収集
    if files:
        upload_files = [str(target_dir / f) for f in files]
    else:
        # 既定ではフォルダ内のすべての .md ファイル
        upload_files = sorted(
            [str(p) for p in target_dir.glob("*.md")],
            key=lambda p: Path(p).name,
        )

    if not upload_files:
        raise ValueError(f"No uploadable files found in {target_dir}")

    print(f"# Found {len(upload_files)} files to upload:", file=sys.stderr)
    for f in upload_files:
        print(f"  - {Path(f).name}", file=sys.stderr)

    email = os.environ.get("NOTEBOOKLM_EMAIL") or os.environ.get("COMPANY_EMAIL") or "admin@livingsupport-matsu.co.jp"
    password = os.environ.get("NOTEBOOKLM_PASSWORD") or ""

    PROFILE_STUDIO.mkdir(parents=True, exist_ok=True)

    result = {
        "ok": False,
        "folder": folder_name,
        "title": title,
        "files": [Path(f).name for f in upload_files],
        "notebook_url": None,
        "notebook_id": None,
    }

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_STUDIO),
            headless=not headed,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            # 1. ログイン確認
            login_if_needed(page, email, password)

            # 2. トップページへ移動
            page.goto("https://notebooklm.google.com/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # 3. 「新規作成」ボタンをクリック
            create_btn = page.locator(
                "button:has-text('新規作成'), [aria-label*='新規作成'], button:has-text('ノートブックを新規作成')"
            ).first
            if not create_btn.count():
                raise RuntimeError("Could not find 'Create notebook' button on home page")

            create_btn.click()
            page.wait_for_timeout(4000)

            notebook_url = page.url.split("?")[0]
            print(f"# Created new notebook: {notebook_url}", file=sys.stderr)
            result["notebook_url"] = notebook_url
            if "/notebook/" in notebook_url:
                result["notebook_id"] = notebook_url.split("/notebook/")[1].split("/")[0]

            # 4. ファイルアップロード
            # 白紙の新規ノートでは、モーダル「ソースを追加」が自動で開いている
            upload_btn = page.locator("button:has-text('ファイルをアップロード'), [aria-label*='ファイルをアップロード']").first
            if not upload_btn.count():
                # 開いていない場合は「ソースを追加」をクリック
                add_src_btn = page.locator("button:has-text('ソースを追加')").first
                if add_src_btn.count():
                    add_src_btn.click()
                    page.wait_for_timeout(2000)
                upload_btn = page.locator("button:has-text('ファイルをアップロード'), [aria-label*='ファイルをアップロード']").first

            if not upload_btn.count():
                raise RuntimeError("Could not find 'ファイルをアップロード' button in modal")

            with page.expect_file_chooser() as fc_info:
                upload_btn.click()
            file_chooser = fc_info.value
            file_chooser.set_files(upload_files)
            print(f"# Set {len(upload_files)} files. Waiting for ingestion...", file=sys.stderr)

            # ソースチップが生成されるのを待機（最大60秒）
            for _ in range(30):
                page.wait_for_timeout(2000)
                # ソース一覧パネル内のソース行を確認
                body_text = page.inner_text("body")
                if any(Path(f).name in body_text for f in upload_files):
                    print("# Source files appeared on page!", file=sys.stderr)
                    break

            page.wait_for_timeout(3000)

            # 5. タイトルの変更（指定がある場合）
            if title:
                title_input = page.locator("input.title-input, [aria-label*='タイトル'], [aria-label*='title' i]").first
                if title_input.count():
                    try:
                        title_input.click()
                        page.keyboard.press("Meta+A")
                        page.keyboard.press("Backspace")
                        title_input.fill(title)
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(1500)
                        print(f"# Renamed notebook title to: {title}", file=sys.stderr)
                    except Exception as e:
                        print(f"# Warning: Failed to rename title: {e}", file=sys.stderr)

            result["ok"] = True
            return result

        finally:
            context.close()


def main():
    parser = argparse.ArgumentParser(description="Create NotebookLM notebook and upload Drive sources")
    parser.add_argument("--folder", required=True, help="Folder name under 200_NoteBookLM")
    parser.add_argument("--title", help="Notebook title")
    parser.add_argument("--files", nargs="*", help="Specific filenames to upload (default: all *.md)")
    parser.add_argument("--headed", action="store_true", help="Run headed browser")

    args = parser.parse_args()
    res = create_and_upload(
        folder_name=args.folder,
        title=args.title,
        files=args.files,
        headed=args.headed,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
