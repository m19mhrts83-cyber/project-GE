#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google カレンダーに予定を1件登録する。

認証: credentials.json + token_calendar.json（Gmail 用 token.json とは分離）

使い方:
  python google_calendar_create.py --title "テスト" --start "2026-06-15 10:00"
  python google_calendar_create.py --title "テスト" --start "2026-06-15 10:00" --end "2026-06-15 11:00"
  python google_calendar_create.py --title "テスト" --start "2026-06-15 10:00" --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCRIPT_DIR = Path(__file__).resolve().parent
CREDENTIALS_PATH = SCRIPT_DIR / "credentials.json"
TOKEN_PATH = SCRIPT_DIR / "token_calendar.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TZ = ZoneInfo("Asia/Tokyo")


def _parse_dt(text: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text.strip(), fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    raise ValueError(f"日時の形式が不正です: {text!r} （例: 2026-06-15 10:00）")


def _oauth_flow_kwargs(login_hint: str | None) -> dict:
    if login_hint:
        return {"authorization_url_kwargs": {"login_hint": login_hint, "prompt": "consent"}}
    return {"prompt": "consent"}


def _load_credentials(*, login_hint: str | None = None, auth_console: bool = False) -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        creds_data = dict(data)
        if "client_id" not in creds_data and CREDENTIALS_PATH.exists():
            client = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
            installed = client.get("installed") or client.get("web", {})
            creds_data["client_id"] = installed.get("client_id")
            creds_data["client_secret"] = installed.get("client_secret")
            creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
            if "access_token" in creds_data and "token" not in creds_data:
                creds_data["token"] = creds_data["access_token"]
        try:
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
        except Exception:
            creds = None

    refreshed = False
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            refreshed = True
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(f"credentials.json が見つかりません: {CREDENTIALS_PATH}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        if auth_console:
            print(
                "認証 URL をシークレットウィンドウで開き、表示されたコードをここに貼り付けてください。",
                file=sys.stderr,
            )
            creds = flow.run_console(**_oauth_flow_kwargs(login_hint))
        else:
            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                **_oauth_flow_kwargs(login_hint),
            )
        refreshed = True

    if refreshed:
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        print(f"token を保存しました: {TOKEN_PATH.name}", file=sys.stderr)

    return creds


def _event_body(title: str, start: datetime, end: datetime, location: str | None, description: str | None) -> dict:
    body: dict = {
        "summary": title,
        "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "Asia/Tokyo"},
    }
    if location:
        body["location"] = location
    if description:
        body["description"] = description
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description="Google カレンダーに予定を登録")
    parser.add_argument("--title", required=True, help="予定タイトル")
    parser.add_argument("--start", required=True, help="開始日時（例: 2026-06-15 10:00）")
    parser.add_argument("--end", help="終了日時（省略時は開始から60分）")
    parser.add_argument("--duration-minutes", type=int, default=60, help="終了未指定時の長さ（分）")
    parser.add_argument("--location", help="場所")
    parser.add_argument("--description", help="説明")
    parser.add_argument("--calendar-id", default="primary", help="カレンダー ID（既定: primary）")
    parser.add_argument("--dry-run", action="store_true", help="登録せず内容だけ表示")
    parser.add_argument(
        "--login-hint",
        help="OAuth 時に使う Google アカウント（例: personal@gmail.com）。会社アカウントに引っ張られるときに指定",
    )
    parser.add_argument(
        "--auth-console",
        action="store_true",
        help="ブラウザ自動起動せず、URL+コード貼り付けで認証（シークレットウィンドウ向け）",
    )
    args = parser.parse_args()

    start = _parse_dt(args.start)
    end = _parse_dt(args.end) if args.end else start + timedelta(minutes=args.duration_minutes)
    if end <= start:
        print("終了日時は開始より後にしてください。", file=sys.stderr)
        return 1

    body = _event_body(args.title, start, end, args.location, args.description)
    print("登録内容:")
    print(f"  タイトル: {args.title}")
    print(f"  開始: {start.strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)")
    print(f"  終了: {end.strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)")
    print(f"  カレンダー: {args.calendar_id}")

    if args.dry_run:
        print("dry-run のため登録しません。")
        return 0

    try:
        creds = _load_credentials(login_hint=args.login_hint, auth_console=args.auth_console)
        service = build("calendar", "v3", credentials=creds)
    except Exception as exc:
        print(f"認証エラー: {exc}", file=sys.stderr)
        return 1

    try:
        me = service.calendarList().get(calendarId="primary").execute()
        print(f"  登録先: {me.get('summary', 'primary')}")
    except Exception:
        pass

    try:
        created = (
            service.events()
            .insert(calendarId=args.calendar_id, body=body)
            .execute()
        )
    except Exception as exc:
        msg = str(exc)
        if "accessNotConfigured" in msg or "has not been used in project" in msg:
            print(
                "Calendar API が credentials.json の GCP プロジェクトで未有効です。\n"
                "個人アカウントでシークレットウィンドウを開き、次を有効化してください:\n"
                "https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview?project=988579281735",
                file=sys.stderr,
            )
        print(f"登録エラー: {exc}", file=sys.stderr)
        return 1

    link = created.get("htmlLink", "")
    print(f"登録しました: {created.get('summary')} ({created.get('id')})")
    if link:
        print(f"URL: {link}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
