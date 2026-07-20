#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Sheets / Drive API の初回 OAuth と接続確認。

使い方:
  python google_workspace_setup.py
  python google_workspace_setup.py --auth-console --login-hint matsuno.estate@gmail.com
  python google_workspace_setup.py --force-reauth
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from googleapiclient.discovery import build

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from google_workspace_auth import CREDENTIALS_PATH, TOKEN_PATH, load_credentials
from google_workspace_scopes import DEFAULT_LOGIN_HINT

CONFIG_PATH = SCRIPT_DIR / "kamiooya_google_config.yaml"


def _load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Workspace（Sheets/Drive）OAuth 設定")
    parser.add_argument("--login-hint", default=DEFAULT_LOGIN_HINT, help="OAuth login_hint")
    parser.add_argument("--auth-console", action="store_true", help="コンソール認証（URL+コード）")
    parser.add_argument("--force-reauth", action="store_true", help="既存 token を無視して再同意")
    args = parser.parse_args()

    cfg = _load_config()
    hint = (args.login_hint or cfg.get("login_hint") or DEFAULT_LOGIN_HINT).strip()

    print(f"credentials: {CREDENTIALS_PATH}", file=sys.stderr)
    print(f"token:       {TOKEN_PATH}", file=sys.stderr)
    print(f"login_hint:  {hint}", file=sys.stderr)

    creds = load_credentials(
        login_hint=hint,
        auth_console=args.auth_console,
        force_reauth=args.force_reauth,
    )

    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    try:
        about = drive.about().get(fields="user(displayName,emailAddress)").execute()
    except Exception as e:
        err = str(e)
        if "accessNotConfigured" in err or "SERVICE_DISABLED" in err:
            print(
                "\n⚠️ Google Drive API が未有効です。次を開いて「有効にする」を押してください:\n"
                "  https://console.developers.google.com/apis/api/drive.googleapis.com/overview?project=988579281735\n",
                file=sys.stderr,
            )
        raise

    user = about.get("user", {})
    print(f"✅ Drive 接続 OK: {user.get('displayName')} <{user.get('emailAddress')}>")

    sheet_id = (cfg.get("kadai_spreadsheet_id") or "").strip()
    if sheet_id:
        try:
            meta = sheets.spreadsheets().get(spreadsheetId=sheet_id, fields="properties.title").execute()
        except Exception as e:
            err = str(e)
            if "accessNotConfigured" in err or "SERVICE_DISABLED" in err:
                print(
                    "\n⚠️ Google Sheets API が未有効です。次を開いて「有効にする」を押してください:\n"
                    "  https://console.developers.google.com/apis/api/sheets.googleapis.com/overview?project=988579281735\n",
                    file=sys.stderr,
                )
            raise
        title = meta.get("properties", {}).get("title", "?")
        print(f"✅ Sheets 接続 OK: 「{title}」 (id={sheet_id[:12]}…)")
    else:
        print("ℹ️ kamiooya_google_config.yaml に kadai_spreadsheet_id がありません（Sheets テスト省略）")

    granted = sorted(getattr(creds, "scopes", None) or [])
    print("付与スコープ:", json.dumps(granted, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
