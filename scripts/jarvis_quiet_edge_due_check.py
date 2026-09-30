#!/usr/bin/env python3
"""Quiet Edge 次回治療の残り日数 → .jarvis_state/quiet_edge_due.json

ホーム／状況ウォッチ用。残り3日以内で warn（show_banner）。

例:
  python scripts/jarvis_quiet_edge_due_check.py
  python scripts/jarvis_quiet_edge_due_check.py --mark-checked
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".jarvis_state" / "quiet_edge_due.json"
ENV_PATH = ROOT / ".env.jarvis_private"
JST = ZoneInfo("Asia/Tokyo")
WARN_WITHIN_DAYS = 3


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


def fetch_next_session() -> dict | None:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    sb = create_client(url, key)
    res = (
        sb.table("vital_treatment_events")
        .select("session_no,scheduled_at,label,status,note")
        .in_("status", ["scheduled", "planned"])
        .order("session_no")
        .execute()
    )
    rows = res.data or []
    scheduled = [r for r in rows if r.get("status") == "scheduled" and r.get("scheduled_at")]
    if scheduled:
        return scheduled[0]
    planned = [r for r in rows if r.get("status") == "planned"]
    return planned[0] if planned else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark-checked", action="store_true")
    args = ap.parse_args()

    load_env()
    if (os.environ.get("JARVIS_QUIET_EDGE_DUE_DISABLE") or "").strip() == "1":
        print("")
        return 0

    state = load_state()
    if state.get("disabled"):
        print("")
        return 0

    today = today_jst()
    nxt = fetch_next_session()
    if not nxt:
        payload = {
            "version": 1,
            "disabled": False,
            "level": "info",
            "summary": "次回治療枠なし",
            "days_until": None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if args.mark_checked:
            state.update(payload)
            save_state(state)
        print("📎 Quiet Edge\n- 次回治療なし")
        return 0

    status = str(nxt.get("status") or "")
    at_raw = nxt.get("scheduled_at")
    session_no = nxt.get("session_no")
    label = nxt.get("label") or f"第{session_no}回"

    days = None
    at_jst = None
    if at_raw and status == "scheduled":
        dt = datetime.fromisoformat(str(at_raw).replace("Z", "+00:00"))
        at_jst = dt.astimezone(JST)
        days = (at_jst.date() - today).days

    level = "ok"
    if status != "scheduled" or days is None:
        level = "info"
        summary = f"{label} 日程未定"
    elif days < 0:
        level = "attention"
        summary = f"{label} {at_jst.strftime('%m/%d %H:%M')}（{abs(days)}日超過・未完了の可能性）"
    elif days <= WARN_WITHIN_DAYS:
        level = "warn"
        summary = f"{label} あと{days}日（{at_jst.strftime('%m/%d %H:%M')}）"
    else:
        summary = f"{label} あと{days}日（{at_jst.strftime('%m/%d %H:%M')}）"

    payload = {
        "version": 1,
        "disabled": False,
        "level": level,
        "summary": summary,
        "session_no": session_no,
        "label": label,
        "status": status,
        "scheduled_at": at_raw,
        "scheduled_at_jst": at_jst.isoformat() if at_jst else None,
        "days_until": days,
        "warn_within_days": WARN_WITHIN_DAYS,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if args.mark_checked or True:
        # 常に最新を残す（ウォッチ評価用）
        state.update(payload)
        save_state(state)

    print("📎 Quiet Edge 次回")
    print(f"- {summary}")
    print("- Dashboard: /quiet-edge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
