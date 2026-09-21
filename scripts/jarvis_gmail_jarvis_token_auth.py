#!/usr/bin/env python3
"""Jarvis 分身 Gmail（jarvis.livingsupport.matsu@gmail.com）の OAuth token を発行する.

他アカウントと同様、215 マニュアル配下に token_jarvis.json を置く。
読取本線は gmail.readonly（Todoist 通知メール確認用）。215 共通スコープも付与。

  cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル
  ~/selenium_env/venv/bin/python ../../../scripts/jarvis_gmail_jarvis_token_auth.py --auth-console

ログイン画面では必ず jarvis.livingsupport.matsu@gmail.com を選ぶこと。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

MANUAL = Path(__file__).resolve().parents[1] / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
sys.path.insert(0, str(MANUAL))

from gmail_api_scopes import GMAIL_SCOPES_215  # noqa: E402
from google.auth.transport.requests import Request  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

CREDENTIALS = MANUAL / "credentials.json"
TOKEN_PATH = MANUAL / "token_jarvis.json"
DEFAULT_HINT = "jarvis.livingsupport.matsu@gmail.com"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth-console", action="store_true", help="コンソールに URL を出しブラウザで同意")
    ap.add_argument("--login-hint", default=os.environ.get("JARVIS_TODOIST_EMAIL") or DEFAULT_HINT)
    ap.add_argument("--force", action="store_true", help="既存 token があっても再認証")
    args = ap.parse_args()

    if not CREDENTIALS.is_file():
        print(f"ERROR: credentials.json がありません: {CREDENTIALS}", file=sys.stderr)
        return 1

    # load hint from env file if present
    hint = (args.login_hint or "").strip()
    priv = Path.home() / "git-repos" / ".env.jarvis_private"
    if priv.is_file() and hint == DEFAULT_HINT:
        for line in priv.read_text(encoding="utf-8").splitlines():
            if line.startswith("JARVIS_TODOIST_EMAIL="):
                hint = line.split("=", 1)[1].strip() or hint
                break

    creds: Credentials | None = None
    if TOKEN_PATH.is_file() and not args.force:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), GMAIL_SCOPES_215)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            print(f"refreshed: {TOKEN_PATH.name}")

    if not creds or not creds.valid or args.force:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), GMAIL_SCOPES_215)
        if args.auth_console:
            # コンソールフロー（ヘッドレス向け）
            creds = flow.run_console(authorization_prompt_message=(
                f"ブラウザで次の URL を開き、必ず {hint} でログインして許可コードを貼ってください:\n"
                "{{url}}"
            ))
        else:
            creds = flow.run_local_server(
                port=0,
                prompt="consent",
                login_hint=hint,
                authorization_prompt_message=(
                    f"ブラウザが開きます。アカウントは必ず {hint} を選んでください。"
                ),
            )
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        os.chmod(TOKEN_PATH, 0o600)
        print(f"saved: {TOKEN_PATH}")

    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    me = svc.users().getProfile(userId="me").execute().get("emailAddress")
    print(f"whoami: {me}")
    if hint and me and me.lower() != hint.lower():
        print(
            f"WARNING: 期待アカウント {hint} と異なります。--force で再認証してください。",
            file=sys.stderr,
        )
        return 2

    # smoke: Todoist 通知の有無
    res = (
        svc.users()
        .messages()
        .list(userId="me", q="from:todoist.com newer_than:7d", maxResults=5)
        .execute()
    )
    n = len(res.get("messages") or [])
    print(f"todoist mail (7d): {n} hit(s)")
    print("OK: Jarvis Gmail API 連携できました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
