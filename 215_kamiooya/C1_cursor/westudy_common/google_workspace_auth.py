# -*- coding: utf-8 -*-
"""Google Sheets / Drive 用 OAuth（credentials.json + token_google_workspace_estate.json）."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from google_workspace_scopes import (
    DEFAULT_LOGIN_HINT,
    DEFAULT_TOKEN_NAME,
    GOOGLE_WORKSPACE_SCOPES_ESTATE,
)

MANUAL_GITREPOS = Path.home() / "git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル"
MANUAL_ONEDRIVE = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル"
)
CREDENTIALS_PATH = MANUAL_GITREPOS / "credentials.json"
TOKEN_PATH = MANUAL_GITREPOS / DEFAULT_TOKEN_NAME


def _oauth_flow_kwargs(login_hint: str | None) -> dict:
    params: dict = {"prompt": "consent"}
    if login_hint:
        params["login_hint"] = login_hint
    return {"authorization_prompt_params": params}


def _mirror_token_to_onedrive(token_path: Path) -> None:
    if not MANUAL_ONEDRIVE.is_dir():
        return
    dest = MANUAL_ONEDRIVE / token_path.name
    try:
        shutil.copy2(token_path, dest)
        print(f"📎 token ミラー: {dest}", file=sys.stderr)
    except OSError as e:
        print(f"⚠️ OneDrive ミラー失敗: {e}", file=sys.stderr)


def load_credentials(
    *,
    token_path: Path | None = None,
    login_hint: str | None = DEFAULT_LOGIN_HINT,
    auth_console: bool = False,
    force_reauth: bool = False,
) -> Credentials:
    """OAuth トークンを読み込み。無効ならブラウザ／コンソールで再同意。"""
    token_path = token_path or TOKEN_PATH
    scopes = GOOGLE_WORKSPACE_SCOPES_ESTATE
    creds: Credentials | None = None

    if not force_reauth and token_path.is_file():
        data = json.loads(token_path.read_text(encoding="utf-8"))
        creds_data = dict(data)
        if "client_id" not in creds_data and CREDENTIALS_PATH.is_file():
            client = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
            installed = client.get("installed") or client.get("web", {})
            creds_data["client_id"] = installed.get("client_id")
            creds_data["client_secret"] = installed.get("client_secret")
            creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
            if "access_token" in creds_data and "token" not in creds_data:
                creds_data["token"] = creds_data["access_token"]
        try:
            creds = Credentials.from_authorized_user_info(creds_data, scopes)
        except Exception:
            creds = None

    refreshed = False
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            refreshed = True
        except Exception:
            creds = None

    if force_reauth or not creds or not creds.valid:
        if not CREDENTIALS_PATH.is_file():
            raise FileNotFoundError(f"credentials.json が見つかりません: {CREDENTIALS_PATH}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), scopes)
        hint = (login_hint or "").strip() or None
        if auth_console:
            print(
                "認証 URL をブラウザで開き、表示されたコードをここに貼り付けてください。",
                file=sys.stderr,
            )
            creds = flow.run_console(**_oauth_flow_kwargs(hint))
        else:
            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                **_oauth_flow_kwargs(hint),
            )
        refreshed = True

    if refreshed:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        print(f"token を保存しました: {token_path}", file=sys.stderr)
        _mirror_token_to_onedrive(token_path)

    return creds
