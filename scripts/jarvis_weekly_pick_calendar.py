#!/usr/bin/env python3
"""今週の9件（Nody /week）に出す Google カレンダー3週間分を sync_meta に置く（Mac で動かす）。

カレンダーの認証は Mac にしかないので、GHA ではなく launchd（日曜 16:30 と毎朝 6:30）で動かす。
置き場: sync_meta.weekly_pick_calendar（{generated_at, from, to, events:[{date,start,end,all_day,title,kind}]}）
- 家族の予定はタスクではなく「参考」として画面に薄く出す。本文・場所は持ち出さない（件名と時刻だけ）。
- 祝日は日本の祝日カレンダーから。

  ~/selenium_env/venv/bin/python scripts/jarvis_weekly_pick_calendar.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_weekly_pick_calendar.py --publish
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
KEY = "weekly_pick_calendar"
HOLIDAYS = "ja.japanese#holiday@group.v.calendar.google.com"
TODOIST_CAL_HINT = "Todoist"  # Todoist 連携カレンダーはタスクと二重になるので読まない


def window(today: date) -> tuple[date, date]:
    """今日から、割り付ける週（次の月曜から）の3週間後の日曜まで。"""
    monday = today if today.weekday() == 0 else today + timedelta(days=7 - today.weekday())
    return today, monday + timedelta(days=20)


def slim(ev: dict[str, Any], kind: str) -> dict[str, Any] | None:
    if ev.get("status") == "cancelled":
        return None
    s, e = ev.get("start") or {}, ev.get("end") or {}
    if "date" in s:
        start = s["date"]
        return {"date": start, "start": None, "end": None, "all_day": True,
                "title": (ev.get("summary") or "(無題)")[:60], "kind": kind,
                "end_date": (date.fromisoformat(e.get("date", start)) - timedelta(days=1)).isoformat()}
    st = datetime.fromisoformat(s.get("dateTime")).astimezone(JST)
    en = datetime.fromisoformat(e.get("dateTime") or s.get("dateTime")).astimezone(JST)
    return {"date": st.date().isoformat(), "start": st.strftime("%H:%M"), "end": en.strftime("%H:%M"),
            "all_day": False, "title": (ev.get("summary") or "(無題)")[:60], "kind": kind}


def classify(title: str) -> str:
    """家族（子ども・学校・塾・通院）か、それ以外か。色分けだけに使う"""
    fam = ("珠己", "円香", "日能研", "中学", "高校", "説明会", "入試", "運動会", "クリニック", "家族", "学校")
    return "family" if any(k in title for k in fam) else "event"


def fetch(today: date, login_hint: str) -> list[dict[str, Any]]:
    manual = Path(__file__).resolve().parents[1] / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
    sys.path.insert(0, str(manual))
    from google_calendar_create import _load_credentials  # noqa: PLC0415
    from googleapiclient.discovery import build  # noqa: PLC0415

    svc = build("calendar", "v3", credentials=_load_credentials(login_hint=login_hint, auth_console=False))
    a, b = window(today)
    tmin, tmax = f"{a.isoformat()}T00:00:00+09:00", f"{(b + timedelta(days=1)).isoformat()}T00:00:00+09:00"
    out: list[dict[str, Any]] = []
    for cal, kind in (("primary", None), (HOLIDAYS, "holiday")):
        token = None
        for _ in range(5):
            resp = svc.events().list(calendarId=cal, timeMin=tmin, timeMax=tmax, singleEvents=True,
                                     orderBy="startTime", maxResults=250, pageToken=token).execute()
            for ev in resp.get("items") or []:
                k = kind or classify(ev.get("summary") or "")
                row = slim(ev, k)
                if row:
                    out.append(row)
            token = resp.get("nextPageToken")
            if not token:
                break
    out.sort(key=lambda r: (r["date"], r["start"] or ""))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--publish", action="store_true", help="sync_meta に置く")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--login-hint", default="admin@livingsupport-matsu.co.jp")
    a = ap.parse_args(argv)
    today = datetime.now(JST).date()
    events = fetch(today, a.login_hint)
    f, t = window(today)
    value = {"generated_at": datetime.now(JST).isoformat(timespec="seconds"), "from": f.isoformat(), "to": t.isoformat(), "events": events}
    print(f"calendar: {f}〜{t} {len(events)} 件")
    if a.dry_run or not a.publish:
        print(json.dumps(events[:20], ensure_ascii=False, indent=1))
        return 0
    from supabase import create_client  # noqa: PLC0415

    sb = create_client(os.environ["JARVIS_SUPABASE_URL"], os.environ["JARVIS_SUPABASE_SERVICE_ROLE_KEY"])
    sb.table("sync_meta").upsert({"key": KEY, "value": json.dumps(value, ensure_ascii=False),
                                  "updated_at": datetime.now(JST).isoformat()}, on_conflict="key").execute()
    print("published sync_meta." + KEY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
