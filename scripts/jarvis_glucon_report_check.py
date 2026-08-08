#!/usr/bin/env python3
"""グルコン提出期限ウォッチ → .jarvis_state/glucon_report.json

状況ウォッチ用。Dashboard /glucon と整合するよう期限近傍を判定する。

例:
  python scripts/jarvis_glucon_report_check.py
  python scripts/jarvis_glucon_report_check.py --mark-checked
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".jarvis_state" / "glucon_report.json"
ENV_PATH = ROOT / ".env.jarvis_private"
JST = ZoneInfo("Asia/Tokyo")
TITLE_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*グルコン")


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def today_jst() -> date:
    return datetime.now(JST).date()


def add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"version": 1, "disabled": False}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "disabled": False}


def save_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def fetch_schedule_from_jarvis() -> list[dict]:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return []
    sb = create_client(url, key)
    res = (
        sb.table("glucon_schedule")
        .select("glucon_date, report_deadline, title, source")
        .order("glucon_date")
        .execute()
    )
    return res.data or []


def fetch_lessons_from_kamiooya() -> list[dict]:
    from supabase import create_client

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return []
    sb = create_client(url, key)
    res = (
        sb.table("comments")
        .select("comment_id, lesson_title")
        .eq("course_tab", "神大家4.グルコン")
        .eq("source_kind", "lesson_desc")
        .limit(200)
        .execute()
    )
    out: list[dict] = []
    for r in res.data or []:
        m = TITLE_DATE_RE.search(r.get("lesson_title") or "")
        if not m:
            continue
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        gd = date(y, mo, d)
        out.append(
            {
                "glucon_date": gd.isoformat(),
                "report_deadline": add_days(gd, -10).isoformat(),
                "title": (r.get("lesson_title") or "")[:180],
                "source": "scraped",
            }
        )
    out.sort(key=lambda x: x["glucon_date"])
    return out


def draft_status(period_key: str) -> dict[str, str]:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return {}
    sb = create_client(url, key)
    res = (
        sb.table("glucon_report_drafts")
        .select("kind, status")
        .eq("period_key", period_key)
        .execute()
    )
    return {r["kind"]: r["status"] for r in (res.data or [])}


def pick_cycle(rows: list[dict], today: date) -> dict | None:
    if not rows:
        return None
    upcoming = next(
        (r for r in rows if date.fromisoformat(r["glucon_date"]) >= today),
        None,
    )
    if not upcoming:
        last = rows[-1]
        est = add_days(date.fromisoformat(last["glucon_date"]), 30)
        if est <= today:
            est = add_days(today, 20)
        upcoming = {
            "glucon_date": est.isoformat(),
            "report_deadline": add_days(est, -10).isoformat(),
            "title": f"推定: 前回 {last['glucon_date']} +30日",
            "source": "estimated",
        }
    idx = next(
        (
            i
            for i, r in enumerate(rows)
            if r["glucon_date"] == upcoming["glucon_date"]
        ),
        -1,
    )
    prev = rows[idx - 1] if idx > 0 else None
    if prev is None:
        earlier = [r for r in rows if r["glucon_date"] < upcoming["glucon_date"]]
        prev = earlier[-1] if earlier else None
    period_key = upcoming["glucon_date"][:7]
    return {
        "glucon_date": upcoming["glucon_date"],
        "report_deadline": upcoming["report_deadline"],
        "title": upcoming.get("title") or "",
        "source": upcoming.get("source") or "scraped",
        "prev_deadline": prev["report_deadline"] if prev else None,
        "period_key": period_key,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark-checked", action="store_true")
    args = ap.parse_args()

    load_env()
    if (os.environ.get("JARVIS_GLUCON_REPORT_DISABLE") or "").strip() == "1":
        print("")
        return 0

    state = load_state()
    if state.get("disabled"):
        print("")
        return 0

    today = today_jst()
    rows = fetch_schedule_from_jarvis() or fetch_lessons_from_kamiooya()
    cycle = pick_cycle(rows, today)
    if not cycle:
        payload = {
            "version": 1,
            "level": "info",
            "summary": "グルコン日程未取得",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if args.mark_checked:
            state.update(payload)
            save_state(state)
        print("📎 グルコン報告\n- 日程未取得（WeStudy取込 or /glucon で手動設定）")
        return 0

    deadline = date.fromisoformat(cycle["report_deadline"])
    days = (deadline - today).days
    statuses = draft_status(cycle["period_key"])
    activity = statuses.get("activity") or "none"
    result = statuses.get("result") or "none"
    activity_done = activity in ("posted", "skipped")
    result_done = result in ("posted", "skipped")

    level = "ok"
    summary_bits = [
        f"開催 {cycle['glucon_date']}",
        f"期限 {cycle['report_deadline']}",
        f"残り{days}日" if days >= 0 else f"{abs(days)}日超過",
        f"活動={activity}",
        f"成果={result}",
    ]
    if not activity_done:
        if days < 0:
            level = "attention"
        elif 0 <= days <= 7:
            level = "warn"
        elif 0 <= days <= 14:
            level = "info"

    payload = {
        "version": 1,
        "disabled": False,
        "level": level,
        "summary": " / ".join(summary_bits),
        "glucon_date": cycle["glucon_date"],
        "report_deadline": cycle["report_deadline"],
        "period_key": cycle["period_key"],
        "days_until_deadline": days,
        "activity_status": activity,
        "result_status": result,
        "activity_done": activity_done,
        "result_done": result_done,
        "source": cycle["source"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if args.mark_checked:
        state.update(payload)
        save_state(state)

    if level == "ok" and activity_done:
        print("")
        return 0

    print("📎 グルコン報告")
    print(f"- 次回グルコン: {cycle['glucon_date']}（{cycle['source']}）")
    print(f"- 提出期限: {cycle['report_deadline']}（残り {days} 日）")
    print(f"- 下書き: 活動={activity} / 成果={result}")
    print("- Dashboard: /glucon")
    if not activity_done and 0 <= days <= 7:
        print("- 次の一手: Journal sync → 下書き生成 → 確認後に WeStudy 投稿")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
