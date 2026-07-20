#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apps Script API で GAS 関数を実行する（initializeSheets / runScoring 等）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

MANUAL_DIR = Path.home() / "git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル"
CREDENTIALS_PATH = MANUAL_DIR / "credentials.json"
DEFAULT_LOGIN_HINT = "matsuno.estate@gmail.com"

SCOPES = [
    "https://www.googleapis.com/auth/script.scriptapp",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def token_path_for(login_hint: str) -> Path:
    local = login_hint.split("@")[0].replace(".", "_")
    return MANUAL_DIR / f"token_saiten_run_{local}.json"


def load_credentials(*, login_hint: str, force_reauth: bool) -> Credentials:
    token_path = token_path_for(login_hint)
    creds: Credentials | None = None
    if not force_reauth and token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        print(f"ブラウザで OAuth 同意してください（{login_hint}）", file=sys.stderr)
        creds = flow.run_local_server(
            port=0,
            access_type="offline",
            authorization_prompt_params={"login_hint": login_hint, "prompt": "consent"},
        )
        token_path.write_text(creds.to_json(), encoding="utf-8")
        print(f"token を保存: {token_path}", file=sys.stderr)
    return creds


def run_function(script, script_id: str, function: str, parameters: list | None = None) -> dict:
    body: dict = {"function": function}
    if parameters:
        body["parameters"] = parameters
    return script.scripts().run(scriptId=script_id, body=body).execute()


def main() -> int:
    parser = argparse.ArgumentParser(description="GAS 関数を API 実行")
    parser.add_argument("--script-id", required=True)
    parser.add_argument("--function", default="initializeSheets")
    parser.add_argument("--login-hint", default=DEFAULT_LOGIN_HINT)
    parser.add_argument("--force-reauth", action="store_true")
    args = parser.parse_args()

    creds = load_credentials(login_hint=args.login_hint, force_reauth=args.force_reauth)
    script = build("script", "v1", credentials=creds, cache_discovery=False)

    try:
        result = run_function(script, args.script_id, args.function)
    except Exception as e:
        err = str(e)
        if "Authorization" in err or "PERMISSION_DENIED" in err:
            print(
                "\n⚠️ GAS の初回権限が未許可の可能性があります。\n"
                "  Apps Script エディタを開き、initializeSheets を1回手動実行して「許可」してください:\n"
                f"  https://script.google.com/home/projects/{args.script_id}/edit\n",
                file=sys.stderr,
            )
        raise

    if result.get("error"):
        details = result["error"].get("details", [])
        msg = details[0].get("errorMessage", str(result["error"])) if details else str(result["error"])
        print(f"❌ GAS 実行エラー: {msg}", file=sys.stderr)
        if "Authorization" in msg or "permission" in msg.lower():
            print(
                f"  → エディタで {args.function} を手動実行し、権限を許可してください。",
                file=sys.stderr,
            )
        return 1

    print(f"✅ {args.function} 実行完了")
    if result.get("response"):
        print(f"   戻り値: {json.dumps(result['response'], ensure_ascii=False)[:500]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
