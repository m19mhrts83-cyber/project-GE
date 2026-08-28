#!/usr/bin/env python3
"""今日（JST）の Google カレンダー予定一覧（admin primary）。

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/google_calendar_today.py
  ~/selenium_env/venv/bin/python scripts/google_calendar_today.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
MANUAL = (
    Path(__file__).resolve().parents[1]
    / "215_kamiooya"
    / "C1_cursor"
    / "1b_Cursorマニュアル"
)
sys.path.insert(0, str(MANUAL))

from google_calendar_create import _load_credentials  # noqa: E402

from googleapiclient.discovery import build  # noqa: E402


def today_bounds() -> tuple[str, str]:
    now = datetime.now(JST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    fmt = "%Y-%m-%dT%H:%M:%S"
    return start.strftime(fmt), end.strftime(fmt)


def fetch_events(*, login_hint: str = "admin@livingsupport-matsu.co.jp") -> list[dict]:
    creds = _load_credentials(login_hint=login_hint, auth_console=False)
    service = build("calendar", "v3", credentials=creds)
    tmin, tmax = today_bounds()
    resp = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=f"{tmin}+09:00",
            timeMax=f"{tmax}+09:00",
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        )
        .execute()
    )
    items = resp.get("items") or []
    out: list[dict] = []
    for ev in items:
        start = ev.get("start") or {}
        end = ev.get("end") or {}
        out.append(
            {
                "summary": ev.get("summary") or "(無題)",
                "start": start.get("dateTime") or start.get("date") or "",
                "end": end.get("dateTime") or end.get("date") or "",
                "location": ev.get("location") or "",
            }
        )
    return out


def format_md(events: list[dict], day: str) -> str:
    lines = [f"# 本日の予定（{day} · admin カレンダー）", ""]
    if not events:
        lines.append("- （予定なし）")
        return "\n".join(lines) + "\n"
    for ev in events:
        t = ev["start"].replace("T", " ")[:16] if ev["start"] else "終日"
        loc = f" @ {ev['location']}" if ev.get("location") else ""
        lines.append(f"- **{t}** {ev['summary']}{loc}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="List today's calendar events (JST)")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument(
        "--login-hint",
        default="admin@livingsupport-matsu.co.jp",
        help="OAuth login hint",
    )
    args = ap.parse_args()
    day = datetime.now(JST).strftime("%Y-%m-%d")
    try:
        events = fetch_events(login_hint=args.login_hint)
    except Exception as exc:
        print(f"calendar error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"date": day, "events": events}, ensure_ascii=False, indent=2))
        return 0
    print(format_md(events, day))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
