#!/usr/bin/env python3
"""
AMEX ログイン（手動＋2FA 自動）→ セッション保存。

既定: ブラウザで手動ログイン → 2FA 画面で Eメール →「次へ」→ Gmail API 自動入力。
完了後 .amex_storage_state.json を保存。

使い方:
  python amex_login_session.py
  # 2FA 完了後、次回は tax_submit_amex.py --headless が使えます

  # 旧: ID/パスワード自動入力（AMEX が拒否する場合あり）
  python amex_login_session.py --auto-login
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from amex_statement import (
    AMEX_LOGIN_URL,
    DEFAULT_ENV_PATH,
    _load_env_file,
    _login,
    _login_verified,
    _open_login_page,
    save_storage_state,
)

SCRIPT_DIR = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="AMEX ログイン＋セッション保存（手動ログイン＋2FA 自動）")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument(
        "--login-timeout",
        type=int,
        default=600,
        help="手動ログイン・2FA の待機秒数（既定 600）",
    )
    parser.add_argument(
        "--auto-login",
        action="store_true",
        help="ID/パスワードを自動入力して送信（既定は手動ログイン）",
    )
    parser.add_argument(
        "--quiet-sec",
        type=int,
        default=60,
        help="ログイン画面表示後、操作しない待機秒数（既定 60）",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))
    login_id = os.environ.get("AMEX_LOGIN_ID", "")
    password = os.environ.get("AMEX_PASSWORD", "")
    manual_credentials = not args.auto_login

    if args.auto_login and not all([login_id, password]):
        print(
            "エラー: --auto-login には AMEX_LOGIN_ID / AMEX_PASSWORD が必要です。\n"
            f"  → {DEFAULT_ENV_PATH}",
            file=sys.stderr,
        )
        return 1

    with sync_playwright() as pw:
        launch_kw: dict = {"headless": False}
        try:
            launch_kw["channel"] = "chrome"
            launch_kw["args"] = ["--disable-blink-features=AutomationControlled"]
        except Exception:
            pass
        browser = pw.chromium.launch(**launch_kw)
        ctx = browser.new_context(locale="ja-JP", accept_downloads=True)
        page = ctx.new_page()
        try:
            if manual_credentials:
                print("=" * 60)
                print("  AMEX 手動ログイン")
                print(f"  1. ブラウザで {AMEX_LOGIN_URL} を開きます")
                print("  2. ID・パスワードを入力して「ログイン」")
                print("  3. 2FA 画面 → Eメール → 次へ は自動実行")
                print("  4. 完了後セッションを保存します")
                print("=" * 60)
                _login(
                    page,
                    login_id or "",
                    password or "",
                    headed=True,
                    manual_login=True,
                    manual_credentials=True,
                    auth_timeout_sec=args.login_timeout,
                    quiet_sec=args.quiet_sec,
                )
            else:
                _login(
                    page,
                    login_id,
                    password,
                    headed=True,
                    manual_login=True,
                    manual_credentials=False,
                    auth_timeout_sec=args.login_timeout,
                )
        except Exception as e:
            print(f"ログイン失敗: {e}", file=sys.stderr)
            ctx.close()
            browser.close()
            return 1

        if not _login_verified(page):
            print("ログイン検証に失敗しました。", file=sys.stderr)
            ctx.close()
            browser.close()
            return 1

        save_storage_state(ctx)
        ctx.close()
        browser.close()

    print("完了: 次回は tax_submit_amex.py を --headless で実行できます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
