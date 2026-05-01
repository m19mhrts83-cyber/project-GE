#!/usr/bin/env python3
"""
太陽光発電ローン（eオリコ想定）の確認コード（OTP）を Gmail API から取得する。

- SOLAR_LOAN_GMAIL_TOKEN_PATH があればそれを優先（無ければ GMAIL_TOKEN_PATH / token_m19m.json を探索）
- SOLAR_LOAN_GMAIL_EXPECT_EMAIL で token の Gmail アカウントが想定と一致するか検証
- 件名/本文から 6 桁を抽出
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCRIPT_DIR = Path(__file__).resolve().parent
MANUAL_DIR = SCRIPT_DIR.parent / "1b_Cursorマニュアル"

# finance 直下からも 1b_Cursorマニュアル を import できるようにする
if str(MANUAL_DIR) not in sys.path:
    sys.path.insert(0, str(MANUAL_DIR))


def _b64url_decode(s: str) -> str:
    data = (s or "").encode("utf-8")
    missing = (-len(data)) % 4
    if missing:
        data += b"=" * missing
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")


def _env_int_nonneg(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _extract_otp(text: str) -> str:
    blob = (text or "").replace("\u3000", " ")
    m = re.search(r"\b(\d{6})\b", blob)
    return m.group(1) if m else ""


def _message_plain_text_snippet(payload: dict) -> str:
    out: list[str] = []

    def walk(p: dict) -> None:
        if not isinstance(p, dict):
            return
        mime = (p.get("mimeType") or "").lower()
        body = p.get("body") or {}
        data = body.get("data") if isinstance(body, dict) else None
        if mime.startswith("text/plain") and data:
            out.append(_b64url_decode(data))
        for ch in p.get("parts") or []:
            walk(ch)

    walk(payload)
    return "\n".join(out)[:12000]


def _resolve_token_path() -> Path:
    try:
        from gmail_api_scopes import resolve_single_token_path_215
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"gmail_api_scopes の読み込みに失敗: {exc}")

    explicit = False
    env_solar = os.environ.get("SOLAR_LOAN_GMAIL_TOKEN_PATH", "").strip()
    env_gmail = os.environ.get("GMAIL_TOKEN_PATH", "").strip()
    if env_solar:
        token_candidate = Path(env_solar).expanduser()
        explicit = True
    elif env_gmail:
        token_candidate = Path(env_gmail).expanduser()
    else:
        # 既定は m19m（プルデンシャル user1 と同一運用）
        m19m_tok = MANUAL_DIR / "token_m19m.json"
        token_candidate = m19m_tok if m19m_tok.is_file() else (MANUAL_DIR / "token.json")

    return resolve_single_token_path_215(MANUAL_DIR, token_candidate, explicit_via_env=explicit)


def _build_gmail_service():
    try:
        from gmail_api_scopes import token_satisfies_215_scopes
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"gmail_api_scopes の読み込みに失敗: {exc}")
    try:
        from gmail_token_sync import save_token_json_and_sync
    except Exception:
        # finance 単体実行で mail_automation が import できない場合のフォールバック
        def save_token_json_and_sync(token_path, creds_json, *, log_prefix: str = "") -> None:  # type: ignore[misc]
            Path(token_path).write_text(creds_json, encoding="utf-8")

    token_path = _resolve_token_path()
    if not token_path.exists():
        raise RuntimeError(f"Gmail token がありません: {token_path}")

    raw = json.loads(token_path.read_text(encoding="utf-8"))
    if not token_satisfies_215_scopes(raw):
        raise RuntimeError(
            "Gmail token のスコープが不足しています（gmail.readonly / modify / send が必要）。"
            f" token: {token_path}"
        )

    creds_data = dict(raw)
    if "token_uri" not in creds_data:
        creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
    if "access_token" in creds_data and "token" not in creds_data:
        creds_data["token"] = creds_data["access_token"]

    creds = Credentials.from_authorized_user_info(creds_data)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        try:
            save_token_json_and_sync(token_path, creds.to_json(), log_prefix="📎 Gmail token: ")
        except Exception:
            pass

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    prof = service.users().getProfile(userId="me").execute()
    em = (prof.get("emailAddress") or "").strip()
    print(f"📧 Gmail API 利用アカウント: {em}（token: {token_path.name}）", file=sys.stderr)
    expect = os.environ.get(
        "SOLAR_LOAN_GMAIL_EXPECT_EMAIL",
        os.environ.get("PRUDENTIAL_GMAIL_EXPECT_EMAIL", "").strip(),
    ).strip()
    if expect and em and expect.lower() != em.lower():
        raise RuntimeError(
            "Gmail token のアカウントが想定と一致しません。"
            f" expect={expect!r} actual={em!r} token={token_path}"
        )
    return service


def _build_query_variants(*, to_email: str) -> list[str]:
    to = (to_email or "").strip()
    if not to:
        raise RuntimeError("to_email が空です（SOLAR_LOAN_GMAIL_EXPECT_EMAIL を設定してください）。")
    q_override = os.environ.get("SOLAR_LOAN_OTP_GMAIL_QUERY", "").strip()
    if q_override:
        return [q_override]
    subj = os.environ.get("SOLAR_LOAN_OTP_GMAIL_SUBJECT", "確認コード").strip() or "確認コード"
    frm = os.environ.get("SOLAR_LOAN_OTP_GMAIL_FROM", "").strip()
    base = f'to:{to} subject:"{subj}"'
    if frm:
        base = f"{base} from:{frm}"
    # フォールバック（件名揺れ対策）
    return [
        f"{base} newer_than:3d",
        f'to:{to} subject:確認 newer_than:3d',
        f'to:{to} newer_than:3d',
    ]


def poll_solar_otp_from_gmail(
    *,
    to_email: str,
    min_internal_date_ms: int,
    max_wait_s: float | None = None,
    poll_s: float | None = None,
) -> str:
    """
    Gmail API で確認コード通知を検索し、min_internal_date_ms 以降の最新 6 桁を返す。
    """
    max_wait = (
        float(os.environ.get("SOLAR_LOAN_OTP_GMAIL_MAX_WAIT_S", "180") or "180")
        if max_wait_s is None
        else max_wait_s
    )
    poll = (
        float(os.environ.get("SOLAR_LOAN_OTP_GMAIL_POLL_S", "4") or "4")
        if poll_s is None
        else poll_s
    )
    skew_ms = _env_int_nonneg("SOLAR_LOAN_OTP_GMAIL_CLOCK_SKEW_MS", 180000)
    effective_min_ms = max(0, int(min_internal_date_ms) - skew_ms)
    queries = _build_query_variants(to_email=to_email)

    service = _build_gmail_service()
    deadline = time.monotonic() + max(5.0, max_wait)
    best: tuple[int, str] | None = None

    while time.monotonic() < deadline:
        for q in queries:
            resp = service.users().messages().list(userId="me", q=q, maxResults=15).execute()
            mids = [m["id"] for m in resp.get("messages", [])]
            for mid in mids:
                full = service.users().messages().get(userId="me", id=mid, format="full").execute()
                internal = int(full.get("internalDate", "0"))
                if internal < effective_min_ms:
                    continue
                headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
                subj = headers.get("Subject", "")
                snippet = full.get("snippet") or ""
                body_text = _message_plain_text_snippet(full.get("payload") or {})
                code = _extract_otp(subj) or _extract_otp(f"{snippet}\n{body_text}")
                if code:
                    if best is None or internal > best[0]:
                        best = (internal, code)
        if best is not None:
            print("📧 Gmail から確認コードを取得しました（チャットには番号を出しません）。", file=sys.stderr)
            return best[1]
        time.sleep(max(1.0, poll))

    raise RuntimeError(f"Gmail から確認コードを {max_wait}s 以内に取得できませんでした。")

