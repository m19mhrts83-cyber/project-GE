#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""採点自動化 GAS をスプレッドシートにバインドして Code.gs をアップロードする。

使い方:
  python 16_deploy_gas.py --spreadsheet-id 1ZX2x...
  python 16_deploy_gas.py --spreadsheet-id 1ZX2x... --force-reauth
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCRIPT_DIR = Path(__file__).resolve().parent
MANUAL_DIR = Path.home() / "git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル"
CREDENTIALS_PATH = MANUAL_DIR / "credentials.json"
DEFAULT_LOGIN_HINT = "m19m.hrts83@gmail.com"
CODE_GS_PATH = SCRIPT_DIR / "04_gas_Code_V2.1.gs"

APPSSCRIPT_MANIFEST = {
    "timeZone": "Asia/Tokyo",
    "exceptionLogging": "STACKDRIVER",
    "runtimeVersion": "V8",
}


def build_project_content(code: str) -> dict:
    return {
        "files": [
            {"name": "Code", "type": "SERVER_JS", "source": code},
            {
                "name": "appsscript",
                "type": "JSON",
                "source": json.dumps(APPSSCRIPT_MANIFEST, ensure_ascii=False),
            },
        ]
    }

SCOPES = [
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def token_path_for(login_hint: str) -> Path:
    local = login_hint.split("@")[0].replace(".", "_")
    return MANUAL_DIR / f"token_saiten_gas_{local}.json"


def load_gas_credentials(*, login_hint: str, force_reauth: bool = False) -> Credentials:
    token_path = token_path_for(login_hint)
    legacy = MANUAL_DIR / "token_saiten_gas.json"
    creds: Credentials | None = None
    if not force_reauth:
        for path in (token_path, legacy if "estate" in login_hint else None):
            if path and path.is_file():
                creds = Credentials.from_authorized_user_file(str(path), SCOPES)
                break
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


def share_spreadsheet_with(drive, spreadsheet_id: str, email: str) -> None:
    drive.permissions().create(
        fileId=spreadsheet_id,
        body={"type": "user", "role": "writer", "emailAddress": email},
        sendNotificationEmail=False,
        fields="id",
    ).execute()
    print(f"📎 スプレッドシートを {email} に編集者共有しました", file=sys.stderr)


def find_bound_project(script, spreadsheet_id: str) -> str | None:
    """既存のバインドプロジェクトを検索。"""
    # Apps Script API には parent で一覧する公式エンドポイントが弱いため、
    # 新規作成を試み、409 相当は手動確認に委ねる。
    return None


def deploy_code(script, spreadsheet_id: str, code: str) -> str:
    project_body = {"title": "WeStudy採点自動化", "parentId": spreadsheet_id}
    try:
        project = script.projects().create(body=project_body).execute()
    except Exception as e:
        err = str(e)
        if "409" in err or "already" in err.lower():
            raise RuntimeError(
                "このスプレッドシートには既に Apps Script がバインドされています。"
                " 拡張機能→Apps Script で Code.gs を手動置換するか、空のプロジェクトを削除して再実行してください。"
            ) from e
        raise
    script_id = project["scriptId"]
    print(f"Apps Script プロジェクト作成: {script_id}", file=sys.stderr)

    content = build_project_content(code)
    script.projects().updateContent(scriptId=script_id, body=content).execute()
    print(f"Code.gs アップロード完了 ({len(code)} 文字, runtime=V8)", file=sys.stderr)
    return script_id


def update_existing(script, script_id: str, code: str) -> str:
    content = build_project_content(code)
    script.projects().updateContent(scriptId=script_id, body=content).execute()
    print(f"既存プロジェクト更新: {script_id} (runtime=V8)", file=sys.stderr)
    return script_id


def main() -> int:
    parser = argparse.ArgumentParser(description="GAS デプロイ")
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument(
        "--script-id",
        default="",
        help="既存 Apps Script ID（指定時は新規作成せず updateContent のみ）",
    )
    parser.add_argument("--login-hint", default=DEFAULT_LOGIN_HINT, help="OAuth ログインアカウント")
    parser.add_argument("--force-reauth", action="store_true")
    parser.add_argument(
        "--share-with",
        default="",
        help="デプロイ前にスプレッドシートを編集者共有するメール（estate 側 token で drive 共有）",
    )
    args = parser.parse_args()

    if not CODE_GS_PATH.is_file():
        print(f"❌ {CODE_GS_PATH} がありません", file=sys.stderr)
        return 1

    if args.share_with:
        import sys as _sys
        _westudy = SCRIPT_DIR.parent.parent / "westudy_common"
        if str(_westudy) not in _sys.path:
            _sys.path.insert(0, str(_westudy))
        from google_workspace_auth import load_credentials as load_estate_creds

        estate = load_estate_creds()
        drive = build("drive", "v3", credentials=estate, cache_discovery=False)
        try:
            share_spreadsheet_with(drive, args.spreadsheet_id, args.share_with)
        except Exception as e:
            print(f"⚠️ 共有スキップ（手動で {args.share_with} に編集者共有してください）: {e}", file=sys.stderr)

    code = CODE_GS_PATH.read_text(encoding="utf-8")
    creds = load_gas_credentials(login_hint=args.login_hint, force_reauth=args.force_reauth)
    script = build("script", "v1", credentials=creds, cache_discovery=False)

    try:
        if args.script_id:
            script_id = update_existing(script, args.script_id, code)
        else:
            script_id = deploy_code(script, args.spreadsheet_id, code)
    except Exception as e:
        err = str(e)
        if "already exists" in err.lower() or "409" in err:
            print("⚠️ 既存のバインドプロジェクトがある可能性があります。", file=sys.stderr)
            print("   スプレッドシート → 拡張機能 → Apps Script で Code.gs を手動置換してください。", file=sys.stderr)
            return 2
        if "accessNotConfigured" in err or "SERVICE_DISABLED" in err:
            print(
                "\n⚠️ GCP プロジェクトで Apps Script API を有効化してください（オーナー m19m.hrts83@gmail.com）:\n"
                "  https://console.cloud.google.com/apis/library/script.googleapis.com?project=yaritori-gmail-487109\n",
                file=sys.stderr,
            )
        elif "script.google.com/home/usersettings" in err:
            print(
                f"\n⚠️ デプロイに使う Google アカウント（{args.login_hint}）で"
                " Apps Script API をユーザー設定から ON にしてください:\n"
                "  https://script.google.com/home/usersettings\n"
                "  →「Google Apps Script API」をオン → 保存後 1〜2 分待って再実行\n",
                file=sys.stderr,
            )
        raise

    editor = f"https://script.google.com/home/projects/{script_id}/edit"
    ss_url = f"https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit"
    print("")
    print("✅ GAS デプロイ完了")
    print(f"   スプレッドシート: {ss_url}")
    print(f"   Apps Script: {editor}")
    print("   スプレッドシートを再読込すると「採点自動化」メニューが表示されます。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
