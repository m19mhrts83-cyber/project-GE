#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIMO（Raimo）アプリに管理者ログインし、CSV取込を自動実行する。

必須環境変数:
  LIMO_APP_URL
  LIMO_ADMIN_EMAIL
  LIMO_ADMIN_PASSWORD

任意環境変数:
  LIMO_HEADLESS=1/0 (既定: 1)
  LIMO_UPLOAD_TIMEOUT_SEC (既定: 1800)
  LIMO_SLOW_MO_MS (既定: 0)

使い方:
  python3 upload_csv_to_limo.py --csv /path/to/delta.csv
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import TimeoutError as PwTimeoutError
    from playwright.sync_api import sync_playwright
except Exception as e:  # pragma: no cover
    print(
        "playwright が見つかりません。`pip install playwright` と "
        "`playwright install chromium` を実行してください。\n"
        f"detail: {e}",
        file=sys.stderr,
    )
    raise SystemExit(2)


def get_required_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"環境変数 {key} が未設定です")
    return value


def get_env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no")


def ensure_csv_file(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise RuntimeError(f"CSVファイルが見つかりません: {p}")
    return p


def wait_import_finished(page, timeout_sec: int) -> str:
    """
    importResult のテキストが一定時間変化しなくなるまで待つ。
    """
    deadline = time.time() + timeout_sec
    last_text = ""
    stable_rounds = 0
    started = False
    while time.time() < deadline:
        current = page.locator("#importResult").inner_text(timeout=5000).strip()
        if current:
            started = True
        if current != last_text:
            last_text = current
            stable_rounds = 0
        else:
            stable_rounds += 1

        toast = page.locator("#toast").inner_text(timeout=2000).strip()
        # 完了トーストを優先
        if "CSV取込完了" in toast:
            return current

        # ログが出始めてから 3 回連続で不変なら完了扱い
        if started and stable_rounds >= 3:
            return current
        page.wait_for_timeout(2000)
    raise PwTimeoutError(f"CSV取込の完了待ちがタイムアウトしました（{timeout_sec}秒）")


def parse_result_stats(result_text: str) -> dict:
    ok_count = len(re.findall(r"^OK row=", result_text, flags=re.MULTILINE))
    skip_count = len(re.findall(r"^SKIP dup row=", result_text, flags=re.MULTILINE))
    ng_count = len(re.findall(r"^NG row=", result_text, flags=re.MULTILINE))
    return {"ok": ok_count, "skip": skip_count, "ng": ng_count}


def main() -> int:
    ap = argparse.ArgumentParser(description="LIMO管理画面でCSV取込を自動実行")
    ap.add_argument("--csv", required=True, help="アップロードするCSVパス")
    ap.add_argument(
        "--timeout-sec",
        type=int,
        default=int(os.environ.get("LIMO_UPLOAD_TIMEOUT_SEC", "1800")),
        help="CSV取込の完了待ちタイムアウト秒",
    )
    ap.add_argument(
        "--screenshot-dir",
        default=None,
        help="失敗時/完了時スクリーンショット保存先（任意）",
    )
    args = ap.parse_args()

    csv_path = ensure_csv_file(args.csv)
    app_url = get_required_env("LIMO_APP_URL")
    login_email = get_required_env("LIMO_ADMIN_EMAIL")
    login_password = get_required_env("LIMO_ADMIN_PASSWORD")
    headless = get_env_bool("LIMO_HEADLESS", True)
    slow_mo = int(os.environ.get("LIMO_SLOW_MO_MS", "0"))
    shot_dir = (
        Path(args.screenshot_dir).expanduser().resolve()
        if args.screenshot_dir
        else None
    )
    if shot_dir:
        shot_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(app_url, wait_until="domcontentloaded", timeout=120000)

            # ログイン
            page.locator("#loginEmail").fill(login_email)
            page.locator("#loginPassword").fill(login_password)
            page.locator("#loginSubmitBtn").click()

            # ログイン成功待ち（mainView 表示）
            page.locator("#mainView").wait_for(state="visible", timeout=120000)

            # 管理者タブ（CSV取込）へ
            admin_tab = page.locator("#adminDataTabBtn")
            admin_tab.wait_for(state="visible", timeout=120000)
            admin_tab.click()

            # CSV ファイル選択と取込実行
            file_input = page.locator("#csvFileInput")
            file_input.set_input_files(str(csv_path))
            page.locator("#importCsvBtn").click()

            result_text = wait_import_finished(page, timeout_sec=args.timeout_sec)
            stats = parse_result_stats(result_text)
            toast_text = page.locator("#toast").inner_text(timeout=3000).strip()

            if shot_dir:
                ok_shot = shot_dir / f"limo_import_ok_{int(time.time())}.png"
                page.screenshot(path=str(ok_shot), full_page=True)
                print(f"スクリーンショット保存: {ok_shot}")

            print(
                "LIMO取込完了: "
                f"OK={stats['ok']} / SKIP={stats['skip']} / NG={stats['ng']}"
            )
            if toast_text:
                print(f"トースト: {toast_text}")

            if stats["ng"] > 0:
                print("NG行があるため終了コード1を返します", file=sys.stderr)
                return 1
            return 0
        except PwTimeoutError as e:
            if shot_dir:
                ng_shot = shot_dir / f"limo_import_ng_{int(time.time())}.png"
                try:
                    page.screenshot(path=str(ng_shot), full_page=True)
                    print(f"失敗時スクリーンショット: {ng_shot}", file=sys.stderr)
                except Exception:
                    pass
            print(f"LIMO取込失敗(タイムアウト): {e}", file=sys.stderr)
            return 2
        except Exception as e:
            if shot_dir:
                ng_shot = shot_dir / f"limo_import_ng_{int(time.time())}.png"
                try:
                    page.screenshot(path=str(ng_shot), full_page=True)
                    print(f"失敗時スクリーンショット: {ng_shot}", file=sys.stderr)
                except Exception:
                    pass
            print(f"LIMO取込失敗: {e}", file=sys.stderr)
            return 2
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
