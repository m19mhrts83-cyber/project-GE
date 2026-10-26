#!/usr/bin/env python3
"""夜間トリアージの pending 件数を Slack #ops に短く出す（1日1回）。

night_triage は ops 案件（2026-10-27 松野さん判断）。Todoist には起票せず、
件数が多いとき・queue が止まっているときだけ #ops に出す。
判定は jarvis_situation_watch.eval_night_triage と同じ（pending 5 以上／更新2日以上前）。

  python scripts/jarvis_night_triage_ops_report.py --dry-run
  python scripts/jarvis_night_triage_ops_report.py --post

停止: JARVIS_NIGHT_TRIAGE_OPS_REPORT_DISABLE=1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_night_triage import (  # noqa: E402
    load_queue,
    pending_partner_hint,
    resolve_dashboard_url,
)

JST = ZoneInfo("Asia/Tokyo")
STATE = REPO / ".jarvis_state" / "night_triage_ops_report.json"
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
WARN_PENDING = 5


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return (datetime.now(JST).date() - dt.astimezone(JST).date()).days


def summarize(queue: dict) -> dict:
    items = [
        i for i in (queue.get("items") or [])
        if i.get("status") == "pending" and i.get("kind") != "activity"
    ]
    partner = [i for i in items if i.get("lane") == "partner"]
    return {
        "pending": len(items),
        "partner": len(partner),
        "general": len(items) - len(partner),
        "hint": pending_partner_hint(partner),
        "updated_at": queue.get("updated_at"),
        "stale_days": _days_since(queue.get("updated_at")),
    }


def needs_report(s: dict) -> bool:
    return s["pending"] >= WARN_PENDING or (s["stale_days"] or 0) >= 2


def build_text(s: dict) -> str:
    lines = ["【ops】夜間トリアージ", f"未処理 {s['pending']}件（パートナー {s['partner']}／一般 {s['general']}）"]
    if s["hint"]:
        lines.append(f"パートナー: {s['hint']}")
    if (s["stale_days"] or 0) >= 2:
        lines.append(f"queue の更新が {s['stale_days']}日止まっています")
    lines += ["", "次: ダッシュで送る／見送るを決める"]
    url = resolve_dashboard_url()
    if url.startswith("https://"):
        lines.append(f"<{url}|ダッシュを開く>")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="件数・同日判定を無視")
    args = ap.parse_args()
    if (os.environ.get("JARVIS_NIGHT_TRIAGE_OPS_REPORT_DISABLE") or "").strip() in ("1", "true", "yes"):
        print("⏭ disabled")
        return 0

    s = summarize(load_queue())
    print(f"📎 night_triage pending={s['pending']} stale_days={s['stale_days']}")
    if not args.force and not needs_report(s):
        print("⏭ 少ないので #ops には出さない")
        return 0
    text = build_text(s)
    if args.dry_run or not args.post:
        print("--- dry-run #ops ---\n" + text)
        return 0

    today = datetime.now(JST).strftime("%Y-%m-%d")
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        st = {}
    if not args.force and st.get("last_post_date") == today:
        print("⏭ 本日 #ops に出し済み")
        return 0
    r = subprocess.run(
        [sys.executable, str(POST), "--channel", "ops", "--text", text,
         "--username", "夜間トリアージ"],
        cwd=str(REPO),
        check=False,
    )
    if r.returncode == 0:
        st.update({"last_post_date": today, "last_pending": s["pending"]})
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return int(r.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
