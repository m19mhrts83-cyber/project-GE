#!/usr/bin/env python3
"""送金アシスト用 OTP 取得（Gmail API / Messages SMS）。

値はログ・チャットに出さない。呼び出し元はメモリ上のみで入力し、
監査には otp_obtained bool だけ記録すること。

Usage:
  # ライブラリ: from jarvis_transfer_otp import fetch_otp, NeedsUserOtp
  # CLI（コードを stdout に出す。本番ではランナー経由を推奨）:
  python scripts/jarvis_transfer_otp.py --channel gmail_api --sender-hint 'SBI' --timeout 90
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MESSAGES_DB = Path.home() / "Library/Messages/chat.db"

TOKEN_MAP = {
    "m19m": REPO
    / "215_kamiooya"
    / "C1_cursor"
    / "1b_Cursorマニュアル"
    / "token_m19m.json",
    "admin": REPO
    / "215_kamiooya"
    / "C1_cursor"
    / "1b_Cursorマニュアル"
    / "token_livingsupport.json",
    "estate": REPO
    / "215_kamiooya"
    / "C1_cursor"
    / "1b_Cursorマニュアル"
    / "token_estate.json",
}

OTP_CHANNELS = frozenset(
    {
        "gmail_api",
        "sms_messages",
        "app_onetime_pw",
        "passkey_or_bio",
        "none",
    }
)


class NeedsUserOtp(Exception):
    """アプリ専用 OTP / 生体。Jarvis は入力できない。"""

    def __init__(self, channel: str, hint: str = ""):
        self.channel = channel
        super().__init__(hint or f"user_otp_required:{channel}")


class OtpFetchError(Exception):
    """取得失敗（値は含めない）。"""


def _token_path(account: str) -> Path:
    key = (account or "m19m").strip().lower()
    path = TOKEN_MAP.get(key)
    if path and path.is_file():
        return path
    fallback = TOKEN_MAP["m19m"]
    if fallback.is_file():
        return fallback
    raise OtpFetchError("gmail_token_missing")


def _extract_code(blob: str) -> str | None:
    if not blob:
        return None
    m = re.search(r"(?<!\d)(\d{6})(?!\d)", blob)
    if m:
        return m.group(1)
    m = re.search(r"(?<!\d)(\d{4,8})(?!\d)", blob)
    return m.group(1) if m else None


def _walk_payload(part: dict[str, Any]) -> str:
    out = ""
    body = part.get("body") or {}
    data = body.get("data")
    if part.get("mimeType") == "text/plain" and data:
        out += base64.urlsafe_b64decode(data + "==").decode("utf-8", "replace")
    for sp in part.get("parts") or []:
        out += _walk_payload(sp)
    return out


def fetch_gmail_otp(
    *,
    sender_hint: str = "",
    gmail_account: str = "m19m",
    after_ms: int | None = None,
    lookback_minutes: int = 30,
    timeout_sec: int = 90,
    poll_sec: float = 3.0,
) -> str:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as e:
        raise OtpFetchError("gmail_deps_missing") from e

    token = _token_path(gmail_account)
    creds = Credentials.from_authorized_user_file(
        str(token),
        ["https://www.googleapis.com/auth/gmail.readonly"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)

    hints = [h.strip() for h in re.split(r"[|,]", sender_hint or "") if h.strip()]
    hint_q = " OR ".join(f'"{h}"' for h in hints) if hints else ""
    base = "(認証 OR 確認 OR ワンタイム OR コード OR パスコード OR OTP)"
    q = f"({hint_q}) {base} newer_than:1d" if hint_q else f"{base} newer_than:1d"

    deadline = time.time() + max(5, timeout_sec)
    min_internal = int(after_ms) if after_ms else 0
    while time.time() < deadline:
        res = svc.users().messages().list(userId="me", q=q, maxResults=12).execute()
        for m in res.get("messages") or []:
            full = (
                svc.users()
                .messages()
                .get(userId="me", id=m["id"], format="full")
                .execute()
            )
            internal = int(full.get("internalDate") or 0)
            if min_internal and internal and internal < min_internal:
                continue
            blob = full.get("snippet") or ""
            payload = full.get("payload") or {}
            for h in payload.get("headers") or []:
                if (h.get("name") or "").lower() in ("subject", "from"):
                    blob += " " + (h.get("value") or "")
            blob += " " + _walk_payload(payload)
            if hints and not any(h.lower() in blob.lower() for h in hints):
                continue
            code = _extract_code(blob)
            if code:
                return code
        time.sleep(poll_sec)
    raise OtpFetchError("gmail_otp_timeout")


def fetch_sms_otp(
    *,
    sender_hint: str = "",
    lookback_minutes: int = 15,
    timeout_sec: int = 90,
    poll_sec: float = 3.0,
) -> str:
    if not MESSAGES_DB.is_file():
        raise OtpFetchError("messages_db_missing")

    needles = [h.strip().lower() for h in re.split(r"[|,]", sender_hint or "") if h.strip()]
    if not needles:
        needles = ["認証", "ワンタイム", "確認コード"]

    deadline = time.time() + max(5, timeout_sec)
    while time.time() < deadline:
        try:
            con = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
            cur = con.cursor()
            cur.execute(
                """
                SELECT text FROM message
                WHERE text IS NOT NULL
                  AND datetime(date/1000000000 + strftime('%s','2001-01-01'),
                               'unixepoch', 'localtime')
                      > datetime('now', 'localtime', ?)
                ORDER BY date DESC LIMIT 40
                """,
                (f"-{lookback_minutes} minutes",),
            )
            rows = cur.fetchall()
            con.close()
        except Exception as e:
            raise OtpFetchError("messages_db_unreadable") from e

        for (text,) in rows:
            if not text:
                continue
            low = text.lower()
            if not any(n in low or n in text for n in needles):
                if "認証" not in text and "ワンタイム" not in text:
                    continue
            code = _extract_code(text)
            if code:
                return code
        time.sleep(poll_sec)
    raise OtpFetchError("sms_otp_timeout")


def fetch_otp(
    *,
    otp_channel: str,
    rail_id: str = "",
    sender_hint: str = "",
    gmail_account: str = "m19m",
    after_ms: int | None = None,
    timeout_sec: int = 90,
) -> str | None:
    """チャネルに応じて OTP を返す。app/passkey は NeedsUserOtp。none は None。"""
    ch = (otp_channel or "").strip().lower()
    if ch not in OTP_CHANNELS:
        raise OtpFetchError(f"unknown_channel:{ch}")
    if ch == "none":
        return None
    if ch in ("app_onetime_pw", "passkey_or_bio"):
        raise NeedsUserOtp(ch, rail_id or ch)
    if ch == "gmail_api":
        return fetch_gmail_otp(
            sender_hint=sender_hint,
            gmail_account=gmail_account,
            after_ms=after_ms,
            timeout_sec=timeout_sec,
        )
    if ch == "sms_messages":
        return fetch_sms_otp(sender_hint=sender_hint, timeout_sec=timeout_sec)
    raise OtpFetchError(f"unhandled_channel:{ch}")


def main() -> int:
    p = argparse.ArgumentParser(description="送金アシスト OTP 取得（値はログしない）")
    p.add_argument("--channel", required=True, choices=sorted(OTP_CHANNELS))
    p.add_argument("--rail-id", default="")
    p.add_argument("--sender-hint", default="")
    p.add_argument("--gmail-account", default="m19m")
    p.add_argument("--timeout", type=int, default=90)
    p.add_argument(
        "--print-code",
        action="store_true",
        help="成功時にコードだけ stdout（呼び出し元パイプ用。チャットに貼らない）",
    )
    args = p.parse_args()
    try:
        code = fetch_otp(
            otp_channel=args.channel,
            rail_id=args.rail_id,
            sender_hint=args.sender_hint,
            gmail_account=args.gmail_account,
            timeout_sec=args.timeout,
        )
    except NeedsUserOtp as e:
        print(f"otp_status=needs_user channel={e.channel}", file=sys.stderr)
        return 2
    except OtpFetchError as e:
        print(f"otp_status=failed reason={e}", file=sys.stderr)
        return 1
    print("otp_status=ok otp_obtained=true", file=sys.stderr)
    if args.print_code and code:
        # 意図的に stdout のみ。監査・ジャーナルには書かない。
        sys.stdout.write(code)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
