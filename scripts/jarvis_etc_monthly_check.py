#!/usr/bin/env python3
"""
Jarvis 月次 ETC 確認 — Gmail・jarvis_private・状態ファイルを読み、報告用 JSON を stdout に出す。

使い方:
  python scripts/jarvis_etc_monthly_check.py
  python scripts/jarvis_etc_monthly_check.py --mark-done --window a
  python scripts/jarvis_etc_monthly_check.py --mark-done --window b
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "etc_monthly.json"
PRIVATE_ENV = REPO / ".env.jarvis_private"
GMAIL_DIR = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
VENV_PYTHON = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip('"\'')
    return out


def load_state() -> dict:
    if STATE_PATH.is_file():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    example = REPO / ".jarvis_state" / "etc_monthly.example.json"
    if example.is_file():
        return json.loads(example.read_text(encoding="utf-8"))
    return {"disabled": False}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def active_windows(now: datetime) -> list[str]:
    d = now.day
    wins: list[str] = []
    if 1 <= d <= 8:
        wins.append("a")
    if 19 <= d <= 26:
        wins.append("b")
    return wins


def month_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


def prev_month_key(now: datetime) -> str:
    y, m = now.year, now.month
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def card_expiry_warning(expiry: str) -> str | None:
    """MM/YY or MM/YYYY"""
    if not expiry or "/" not in expiry:
        return None
    a, b = expiry.split("/", 1)
    try:
        mm = int(a)
        yy = int(b)
        if yy < 100:
            yy += 2000
        exp = datetime(yy, mm, 1, tzinfo=JST)
        now = datetime.now(JST)
        months = (exp.year - now.year) * 12 + (exp.month - now.month)
        if months <= 3:
            return f"有効期限 {expiry}（{months}ヶ月以内）"
    except ValueError:
        pass
    return None


def gmail_etc_search(days: int = 45) -> list[dict]:
    cred = GMAIL_DIR / "credentials.json"
    token = GMAIL_DIR / "token.json"
    if not cred.is_file() or not token.is_file():
        return []
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return []

    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    creds = Credentials.from_authorized_user_file(str(token), scopes)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    q = (
        f"newer_than:{days}d "
        '(subject:"ETCマイレージ" OR subject:"ＥＴＣマイレージ" OR subject:"還元" OR from:smile-etc.jp)'
    )
    res = service.users().messages().list(userId="me", q=q, maxResults=10).execute()
    hits = []
    for mid in res.get("messages", [])[:10]:
        msg = service.users().messages().get(userId="me", id=mid["id"], format="metadata").execute()
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        hits.append(
            {
                "date": headers.get("date", ""),
                "subject": headers.get("subject", ""),
            }
        )
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--window", choices=("a", "b"), help="mark-done 時に必須")
    parser.add_argument("--note", default="", help="mark-done 時のメモ")
    parser.add_argument("--ok", action="store_true", help="mark-done 時に OK と記録")
    args = parser.parse_args()

    now = datetime.now(JST)
    env = load_dotenv(PRIVATE_ENV)
    state = load_state()
    disabled = state.get("disabled") or env.get("JARVIS_ETC_MONTHLY_DISABLE", "").strip() in (
        "1",
        "true",
        "yes",
    )

    report: dict = {
        "now_jst": now.isoformat(),
        "month": month_key(now),
        "prev_month": prev_month_key(now),
        "active_windows": active_windows(now),
        "disabled": disabled,
        "mileage_id_set": bool(env.get("ETC_MILEAGE_ID")),
        "mileage_id_tail": (env.get("ETC_MILEAGE_ID") or "")[-4:] or None,
        "meisai_user_set": bool(env.get("ETC_MEISAI_USER_ID")),
        "card_expiry": env.get("ETC_CARD_EXPIRY") or None,
        "card_expiry_warning": card_expiry_warning(env.get("ETC_CARD_EXPIRY", "")),
        "pending_windows": [],
        "gmail_etc": [],
    }

    if disabled:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    mk = month_key(now)
    for w in active_windows(now):
        key = f"last_check_{w}"
        if state.get(key) != mk:
            report["pending_windows"].append(w)

    try:
        report["gmail_etc"] = gmail_etc_search()
    except Exception as e:
        report["gmail_error"] = str(e)

    if args.mark_done and args.window:
        key = f"last_check_{args.window}"
        state[key] = mk
        rk = f"last_result_{args.window}"
        state[rk] = {
            "at": now.isoformat(),
            "ok": args.ok,
            "note": args.note,
        }
        save_state(state)
        report["marked"] = args.window

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
