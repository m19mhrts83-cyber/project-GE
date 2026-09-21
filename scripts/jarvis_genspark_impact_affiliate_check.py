#!/usr/bin/env python3
"""
Jarvis: Genspark（MainFunc PTE.LTD）Impact アフィリエイト審査メール確認。

登録アカウント: m19m.hrts83@gmail.com
state: ~/git-repos/.jarvis_state/genspark_impact_affiliate_watch.json

使い方:
  python scripts/jarvis_genspark_impact_affiliate_check.py
  python scripts/jarvis_genspark_impact_affiliate_check.py --mark-checked
  python scripts/jarvis_genspark_impact_affiliate_check.py --mark-approved
  python scripts/jarvis_genspark_impact_affiliate_check.py --json
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "genspark_impact_affiliate_watch.json"
PRIVATE_ENV = REPO / ".env.jarvis_private"
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"

# 審査・承認系（Google の OAuth 共有通知や Meeting Notes は除外）
QUERY = (
    "in:anywhere newer_than:14d "
    "(from:impact.com OR from:impactradius.com OR from:partner.impact.com "
    "OR from:noreply@impact.com OR (from:genspark.ai subject:(partner OR affiliate OR approved OR approval OR application OR welcome OR review OR joined)) "
    "OR subject:(MainFunc OR \"partner program\" OR \"affiliate\") "
    "(impact OR MainFunc OR Genspark))"
)
NOISE_FROM = ("noreply-accounts@google.com", "noreply@github.com")
NOISE_SUBJECT = ("meeting notes", "ご注文", "invoice", "action required: meeting")


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def load_state() -> dict:
    default = {
        "disabled": False,
        "status": "in_review",
        "applied_at": "2026-09-20",
        "account": "m19m",
        "email": "m19m.hrts83@gmail.com",
        "last_checked_at": None,
        "last_result": None,
        "last_hit_subjects": [],
    }
    if not STATE_PATH.is_file():
        return default
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(data, dict):
        return default
    for k, v in default.items():
        data.setdefault(k, v)
    return data


def save_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _materialize_token() -> tuple[Path, Path]:
    env = {**load_dotenv(PRIVATE_ENV), **os.environ}
    cred_path = MANUAL / "credentials.json"
    tok_path = MANUAL / "token_m19m.json"

    cred_b64 = (env.get("GMAIL_CREDENTIALS_B64") or "").strip()
    tok_b64 = (env.get("GMAIL_M19M_TOKEN_B64") or "").strip()
    tmp = REPO / ".credentials"
    if cred_b64:
        tmp.mkdir(parents=True, exist_ok=True)
        cred_path = tmp / "credentials.json"
        cred_path.write_bytes(base64.b64decode(cred_b64))
    if tok_b64:
        tmp.mkdir(parents=True, exist_ok=True)
        tok_path = tmp / "token_m19m.json"
        tok_path.write_bytes(base64.b64decode(tok_b64))

    if not cred_path.is_file() or not tok_path.is_file():
        raise SystemExit(
            "m19m Gmail credentials/token がありません。"
            " credentials.json + token_m19m.json または GMAIL_*_B64 を用意してください。"
        )
    return cred_path, tok_path


def build_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    cred_path, tok_path = _materialize_token()
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    creds = Credentials.from_authorized_user_file(str(tok_path), scopes)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        tok_path.write_text(creds.to_json(), encoding="utf-8")
    if not creds or not creds.valid:
        raise SystemExit(f"token 無効: {tok_path}")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _header_map(msg: dict) -> dict[str, str]:
    headers = msg.get("payload", {}).get("headers") or []
    return {h["name"]: h["value"] for h in headers if "name" in h and "value" in h}


def _is_noise(frm: str, subject: str) -> bool:
    fl = frm.lower()
    sl = subject.lower()
    if any(n in fl for n in NOISE_FROM):
        return True
    if any(n in sl for n in NOISE_SUBJECT):
        return True
    # Google OAuth 共有通知のみ
    if "google" in fl and "impact.com" in sl and "共有" in subject:
        return True
    return False


def _classify(subject: str, body_snip: str = "") -> str:
    text = f"{subject} {body_snip}".lower()
    if any(k in text for k in ("approved", "approval", "accepted", "welcome", "承認", "承認されました", "joined")):
        return "approved"
    if any(k in text for k in ("reject", "declined", "denied", "却下", "否認")):
        return "rejected"
    if any(k in text for k in ("review", "pending", "application", "applied", "審査", "申請")):
        return "in_review_mail"
    return "other"


def search_hits(service, max_results: int = 15) -> list[dict]:
    res = (
        service.users()
        .messages()
        .list(userId="me", q=QUERY, maxResults=max_results)
        .execute()
    )
    out: list[dict] = []
    for m in res.get("messages") or []:
        full = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=m["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        h = _header_map(full)
        frm = h.get("From", "")
        subject = h.get("Subject", "")
        if _is_noise(frm, subject):
            continue
        date_raw = h.get("Date", "")
        try:
            dt = parsedate_to_datetime(date_raw).astimezone(JST)
            date_s = dt.strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError, IndexError):
            date_s = date_raw[:25]
        kind = _classify(subject)
        out.append(
            {
                "id": m["id"],
                "date": date_s,
                "from": frm[:80],
                "subject": subject[:120],
                "kind": kind,
                "labels": full.get("labelIds") or [],
            }
        )
    return out


def format_block(state: dict, hits: list[dict]) -> str:
    lines = ["📎 Genspark Impact アフィリエイト"]
    if state.get("disabled") or state.get("status") == "approved":
        lines.append(f"状態: ウォッチ終了（status={state.get('status')}）")
        return "\n".join(lines)

    if not hits:
        lines.append("結果: **まだ来ていない**（審査メールなし）")
        lines.append(f"登録: {state.get('applied_at')} / {state.get('email')} / In Review 想定")
    else:
        approved = [h for h in hits if h["kind"] == "approved"]
        rejected = [h for h in hits if h["kind"] == "rejected"]
        if approved:
            lines.append("結果: **承認メールあり**")
        elif rejected:
            lines.append("結果: **却下・否認の可能性**")
        else:
            lines.append("結果: **関連メールあり**（承認確定ではない）")
        for h in hits[:5]:
            lines.append(f"- {h['date']} | {h['kind']} | {h['subject']}")
        if approved:
            lines.append("次: Impact ダッシュボードでトラッキングリンク発行")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark-checked", action="store_true")
    ap.add_argument("--mark-approved", action="store_true", help="承認済みとしてウォッチ無効化")
    ap.add_argument("--mark-disabled", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    env = {**load_dotenv(PRIVATE_ENV), **os.environ}
    if env.get("JARVIS_GENSPARK_IMPACT_AFFILIATE_WATCH_DISABLE") == "1":
        print("📎 Genspark Impact アフィリエイト\n状態: disabled（環境変数）")
        return 0

    state = load_state()
    if args.mark_disabled:
        state["disabled"] = True
        state["status"] = "disabled"
        save_state(state)
        print("📎 Genspark Impact アフィリエイト\n状態: disabled に更新")
        return 0
    if args.mark_approved:
        state["disabled"] = True
        state["status"] = "approved"
        state["last_checked_at"] = datetime.now(JST).isoformat(timespec="seconds")
        save_state(state)
        print("📎 Genspark Impact アフィリエイト\n状態: approved（ウォッチ終了）")
        return 0

    if state.get("disabled"):
        print(format_block(state, []))
        return 0

    try:
        service = build_service()
        hits = search_hits(service)
    except SystemExit as e:
        print(f"📎 Genspark Impact アフィリエイト\nエラー: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"📎 Genspark Impact アフィリエイト\nエラー: {e}")
        return 1

    if args.mark_checked:
        state["last_checked_at"] = datetime.now(JST).isoformat(timespec="seconds")
        state["last_result"] = (
            "approved"
            if any(h["kind"] == "approved" for h in hits)
            else ("hits" if hits else "none")
        )
        state["last_hit_subjects"] = [h["subject"] for h in hits[:5]]
        if any(h["kind"] == "approved" for h in hits):
            state["status"] = "approved_mail_seen"
        save_state(state)

    if args.json:
        print(json.dumps({"state": state, "hits": hits}, ensure_ascii=False, indent=2))
    else:
        print(format_block(state, hits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
