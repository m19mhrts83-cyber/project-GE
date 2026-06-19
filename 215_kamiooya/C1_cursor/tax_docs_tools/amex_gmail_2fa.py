#!/usr/bin/env python3
"""
AMEX 二段階認証コードを Gmail API で取得する。

前提:
  - 215 共通の credentials.json / token.json（gmail.readonly 以上）
  - AMEX の 2FA で「Eメール」ラジオ →「次へ」後、当該 Gmail 宛にコードが届く

環境変数（.env.tax_docs）:
  GMAIL_CREDENTIALS_PATH  未設定時: 1b_Cursorマニュアル/credentials.json
  GMAIL_TOKEN_PATH          未設定時: 1b_Cursorマニュアル/token.json
  AMEX_2FA_GMAIL_DISABLE=1  Gmail 自動取得を無効化
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
MANUAL_DIR = SCRIPT_DIR.parent / "1b_Cursorマニュアル"
MAIL_AUTO = SCRIPT_DIR.parent / "mail_automation"

for p in (MANUAL_DIR, MAIL_AUTO):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gmail_api_scopes import GMAIL_SCOPES_215 as GMAIL_SCOPES, token_satisfies_215_scopes

try:
    from gmail_token_sync import save_token_json_and_sync
except ImportError:

    def save_token_json_and_sync(token_path, creds_json, *, log_prefix: str = "📎 Gmail token") -> None:
        Path(token_path).parent.mkdir(parents=True, exist_ok=True)
        Path(token_path).write_text(creds_json, encoding="utf-8")


DEFAULT_CREDENTIALS = MANUAL_DIR / "credentials.json"
DEFAULT_TOKEN = MANUAL_DIR / "token.json"

# AMEX からの OTP メール想定
_AMEX_FROM_HINTS = ("americanexpress", "amex.com", "aexp.com")
_OTP_PATTERNS = (
    re.compile(r"(?:確認コード|認証コード|verification code|one[- ]time|OTP|パスワード)[^\d]{0,30}(\d{6})", re.I),
    re.compile(r"(?:コード|code)\s*[:：]?\s*(\d{6})", re.I),
    re.compile(r"\b(\d{6})\b"),
)


def _credentials_path() -> Path:
    raw = os.environ.get("GMAIL_CREDENTIALS_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_CREDENTIALS


def _token_path() -> Path:
    raw = os.environ.get("GMAIL_TOKEN_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_TOKEN


def gmail_2fa_enabled() -> bool:
    return os.environ.get("AMEX_2FA_GMAIL_DISABLE", "").strip() not in ("1", "true", "yes")


def build_gmail_service():
    """Gmail API サービスを返す（token 期限切れ時は refresh）。"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    credentials_path = _credentials_path()
    token_path = _token_path()

    if not credentials_path.exists():
        raise FileNotFoundError(f"Gmail credentials が見つかりません: {credentials_path}")
    if not token_path.exists():
        raise FileNotFoundError(f"Gmail token が見つかりません: {token_path}")

    creds = None
    token_data = json.loads(token_path.read_text(encoding="utf-8"))
    creds_data = dict(token_data)
    if "client_id" not in creds_data:
        client = json.loads(credentials_path.read_text(encoding="utf-8"))
        inst = client.get("installed") or client.get("web", {})
        creds_data["client_id"] = inst.get("client_id")
        creds_data["client_secret"] = inst.get("client_secret")
        creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
    if "access_token" in creds_data and "token" not in creds_data:
        creds_data["token"] = creds_data["access_token"]

    if token_satisfies_215_scopes(creds_data):
        creds = Credentials.from_authorized_user_info(creds_data, GMAIL_SCOPES)

    refreshed = False
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        refreshed = True

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), GMAIL_SCOPES)
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
        refreshed = True

    if refreshed:
        save_token_json_and_sync(token_path, creds.to_json())
        print(f"  Gmail token を更新: {token_path.name}")

    service = build("gmail", "v1", credentials=creds)
    return service


def extract_otp_from_text(text: str) -> Optional[str]:
    """メール本文から 6 桁 OTP を抽出。"""
    if not text:
        return None
    for pat in _OTP_PATTERNS:
        m = pat.search(text)
        if m:
            code = m.group(1)
            if len(code) == 6 and code.isdigit():
                return code
    return None


def _message_body(payload: dict) -> str:
    """Gmail message payload からプレーンテキストを再帰取得。"""
    parts: list[str] = []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data and mime in ("text/plain", "text/html"):
            try:
                raw = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                parts.append(raw)
            except Exception:
                pass
        for sub in part.get("parts") or []:
            walk(sub)

    if payload.get("body", {}).get("data"):
        walk(payload)
    for p in payload.get("parts") or []:
        walk(p)

    return "\n".join(parts)


def _message_internal_date(msg: dict) -> float:
    """メッセージの epoch 秒（internalDate 優先）。"""
    internal = msg.get("internalDate")
    if internal:
        try:
            return int(internal) / 1000.0
        except (TypeError, ValueError):
            pass
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    date_hdr = headers.get("date", "")
    if date_hdr:
        try:
            return parsedate_to_datetime(date_hdr).timestamp()
        except Exception:
            pass
    return 0.0


def _is_amex_sender(from_hdr: str) -> bool:
    f = (from_hdr or "").lower()
    return any(h in f for h in _AMEX_FROM_HINTS)


def fetch_amex_otp_from_gmail(
    *,
    not_before_epoch: float,
    timeout_sec: int = 180,
    poll_interval_sec: float = 5.0,
) -> Optional[str]:
    """
    Gmail から AMEX の OTP をポーリング取得する。

    not_before_epoch: この時刻より後に届いたメールのみ対象（パスワード送信直前を渡す）
    """
    if not gmail_2fa_enabled():
        return None

    service = build_gmail_service()
    deadline = time.time() + timeout_sec
    seen_ids: set[str] = set()
    # Gmail newer_than は分単位。余裕を持って 1 日以内に絞る
    query = (
        "newer_than:1d "
        "(from:americanexpress OR from:amex OR from:aexp) "
        "(subject:確認 OR subject:verification OR subject:code OR subject:American OR subject:ワンタイム)"
    )

    print(f"  [Gmail] AMEX 確認コードを待機（最大 {timeout_sec} 秒）…")

    while time.time() < deadline:
        try:
            resp = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=10)
                .execute()
            )
            for stub in resp.get("messages") or []:
                mid = stub["id"]
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
                ts = _message_internal_date(msg)
                if ts and ts < not_before_epoch - 30:
                    continue
                headers = {
                    h["name"].lower(): h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }
                if not _is_amex_sender(headers.get("from", "")):
                    continue
                body = _message_body(msg.get("payload", {}))
                subj = headers.get("subject", "")
                code = extract_otp_from_text(subj + "\n" + body)
                if code:
                    print(f"  [Gmail] 確認コードを取得しました（{headers.get('subject', '')[:60]}）")
                    return code
        except Exception as e:
            print(f"  [Gmail] 取得エラー: {e}", file=sys.stderr)

        time.sleep(poll_interval_sec)

    print("  [Gmail] タイムアウト: 確認コードメールが見つかりませんでした", file=sys.stderr)
    return None
