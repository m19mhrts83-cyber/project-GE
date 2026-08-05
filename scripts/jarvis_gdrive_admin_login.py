#!/usr/bin/env python3
"""
admin Google Drive（readonly）専用 OAuth。

- Gmail / Calendar token に Drive スコープを混ぜない
- 保存先: 215_kamiooya/.../1b_Cursorマニュアル/token_drive_admin.json
- ダッシュボード ask Phase3 用（GDRIVE_REFRESH_TOKEN 等）

使い方:
  cd ~/git-repos
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_gdrive_admin_login.py
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_gdrive_admin_login.py --auth-console
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_gdrive_admin_login.py --print-env
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
CREDENTIALS_PATH = MANUAL / "credentials.json"
TOKEN_PATH = MANUAL / "token_drive_admin.json"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DEFAULT_LOGIN_HINT = "admin@livingsupport-matsu.co.jp"
FOLDER_NAME = "200_NoteBookLM"


def _oauth_url_kwargs(login_hint: str | None) -> dict:
    """run_local_server / authorization_url に渡す kwargs。"""
    kw: dict = {
        "access_type": "offline",
        "prompt": "consent",
        # Drive 専用。true だと既存 Gmail/Calendar 権限が同意画面に混ざる
    }
    if login_hint:
        kw["login_hint"] = login_hint
    return kw


def _client_bits() -> tuple[str, str]:
    raw = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    installed = raw.get("installed") or raw.get("web") or {}
    return (
        str(installed.get("client_id") or "").strip(),
        str(installed.get("client_secret") or "").strip(),
    )


def load_credentials(
    *,
    login_hint: str | None = DEFAULT_LOGIN_HINT,
    auth_console: bool = False,
    port: int = 8099,
) -> Credentials:
    if not CREDENTIALS_PATH.is_file():
        raise FileNotFoundError(f"credentials.json がありません: {CREDENTIALS_PATH}")

    creds: Credentials | None = None
    if TOKEN_PATH.is_file():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        url_kw = _oauth_url_kwargs(login_hint)
        if auth_console:
            print(
                "認証 URL をシークレットウィンドウで開き、admin で同意後にコードを貼ってください。",
                file=sys.stderr,
            )
            # run_console は非推奨気味だがフォールバックとして残す
            creds = flow.run_console(**url_kw)
        else:
            print(
                f"ローカル待ち受け: http://127.0.0.1:{port}/ "
                f"（同意後に Connection failed なら、このプロセスが生きているか確認）",
                file=sys.stderr,
            )
            print(f"使用アカウント: {login_hint}", file=sys.stderr)
            # open_browser=True で正しい redirect_uri の URL を開く（手動 open でポートずれしない）
            creds = flow.run_local_server(
                host="127.0.0.1",
                port=port,
                open_browser=True,
                bind_addr="127.0.0.1",
                **url_kw,
            )
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        print(f"token を保存しました: {TOKEN_PATH}", file=sys.stderr)

    return creds


def resolve_notebooklm_folder_id(creds: Credentials) -> str | None:
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    q = (
        f"name = '{FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    res = (
        svc.files()
        .list(q=q, spaces="drive", fields="files(id,name)", pageSize=10)
        .execute()
    )
    files = res.get("files") or []
    if not files:
        return None
    return str(files[0].get("id") or "") or None


def folder_id_from_url(url: str) -> str | None:
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", url or "")
    return m.group(1) if m else None


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    for key, val in updates.items():
        line = f"{key}={val}"
        if re.search(rf"^{re.escape(key)}=", text, re.M):
            text = re.sub(rf"^{re.escape(key)}=.*$", line, text, count=1, flags=re.M)
        else:
            text = text.rstrip() + f"\n{line}\n"
    path.write_text(text, encoding="utf-8")


def print_env(creds: Credentials, folder_id: str | None) -> None:
    client_id, client_secret = _client_bits()
    refresh = creds.refresh_token or ""
    print("# --- paste into .env.jarvis_private / Vercel ---")
    print(f"GDRIVE_CLIENT_ID={client_id}")
    print(f"GDRIVE_CLIENT_SECRET={client_secret}")
    print(f"GDRIVE_REFRESH_TOKEN={refresh}")
    if folder_id:
        print(f"GDRIVE_NOTEBOOKLM_FOLDER_ID={folder_id}")
    else:
        print("# GDRIVE_NOTEBOOKLM_FOLDER_ID=  # 未解決。Drive で 200_NoteBookLM を確認")


def main() -> int:
    ap = argparse.ArgumentParser(description="admin Drive readonly OAuth")
    ap.add_argument(
        "--login-hint",
        default=DEFAULT_LOGIN_HINT,
        help="OAuth login_hint（既定: admin）",
    )
    ap.add_argument(
        "--auth-console",
        action="store_true",
        help="ブラウザ自動ではなくコンソールコード入力",
    )
    ap.add_argument(
        "--print-env",
        action="store_true",
        help="GDRIVE_* 行を stdout に出す（秘密注意）",
    )
    ap.add_argument(
        "--write-env",
        action="store_true",
        help=".env.jarvis_private に GDRIVE_* を追記／更新",
    )
    ap.add_argument(
        "--folder-url",
        default="",
        help="NOTEBOOKLM_DRIVE_FOLDER_URL があれば ID 抽出に使う",
    )
    ap.add_argument(
        "--port",
        type=int,
        default=8099,
        help="run_local_server の固定ポート（既定 8099。Connection failed 対策）",
    )
    args = ap.parse_args()

    print(f"使用アカウント: {args.login_hint}", file=sys.stderr)
    creds = load_credentials(
        login_hint=args.login_hint or None,
        auth_console=args.auth_console,
        port=args.port,
    )
    if not creds.refresh_token:
        print(
            "refresh_token がありません。token を削除して再同意してください。",
            file=sys.stderr,
        )
        return 1

    folder_id = folder_id_from_url(args.folder_url) if args.folder_url else None
    if not folder_id:
        try:
            folder_id = resolve_notebooklm_folder_id(creds)
        except Exception as e:
            print(f"フォルダ ID 解決失敗: {e}", file=sys.stderr)

    print(f"token: {TOKEN_PATH.name}", file=sys.stderr)
    print(f"folder_id: {folder_id or '(未解決)'}", file=sys.stderr)

    if args.write_env:
        env_path = REPO / ".env.jarvis_private"
        client_id, client_secret = _client_bits()
        updates = {
            "GDRIVE_CLIENT_ID": client_id,
            "GDRIVE_CLIENT_SECRET": client_secret,
            "GDRIVE_REFRESH_TOKEN": creds.refresh_token or "",
        }
        if folder_id:
            updates["GDRIVE_NOTEBOOKLM_FOLDER_ID"] = folder_id
        upsert_env(env_path, updates)
        print(f"updated {env_path.name} (GDRIVE_*)", file=sys.stderr)

    if args.print_env:
        print_env(creds, folder_id)
    elif not args.write_env:
        print(
            "環境変数を出すには --print-env、書き込みは --write-env。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
