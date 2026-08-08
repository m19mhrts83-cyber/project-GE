#!/usr/bin/env python3
"""Quiet Edge: レーザー治療スケジュール更新（Jarvis 本線）.

アプリUIや Journal 自動抽出は使わない。月1回程度、チャットで伝えた内容を
このスクリプトで vital_treatment_events に反映する。

例:
  # 一覧
  python scripts/jarvis_quiet_edge_treatment.py --list

  # 第4回を完了にする
  python scripts/jarvis_quiet_edge_treatment.py --done 4 --at 2026-08-08T15:00

  # 第5回の日程を決めた（予定へ）
  python scripts/jarvis_quiet_edge_treatment.py --schedule 5 --at 2026-09-05T15:00

  # 枠だけ置く（日程未定）
  python scripts/jarvis_quiet_edge_treatment.py --plan 6 --note "経過見て判断"
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from supabase import create_client
except ImportError:
    print("need supabase-py", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.jarvis_private"
JST = ZoneInfo("Asia/Tokyo")
PLANNED_TOTAL_DEFAULT = 9


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def parse_at(raw: str | None) -> str | None:
    """Accept YYYY-MM-DD or YYYY-MM-DDTHH:MM[+09:00]. Return ISO timestamptz."""
    if not raw:
        return None
    s = raw.strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        dt = datetime(int(s[0:4]), int(s[5:7]), int(s[8:10]), 15, 0, tzinfo=JST)
        return dt.isoformat()
    if "T" in s and ("+" in s[10:] or s.endswith("Z")):
        return s
    # local JST without offset
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise SystemExit(f"bad --at: {raw}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.isoformat()


def client():
    load_env()
    url = os.environ.get("JARVIS_SUPABASE_URL") or ""
    key = (
        os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("JARVIS_SUPABASE_SECRET_KEY")
        or ""
    )
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / SERVICE_ROLE_KEY が必要です")
    return create_client(url, key)


def label_for(n: int) -> str:
    return f"第{n}回治療"


def status_ja(st: str) -> str:
    return {
        "done": "完了",
        "scheduled": "予定",
        "planned": "枠（日程未定）",
        "cancelled": "中止",
    }.get(st, st)


def cmd_list(sb) -> int:
    r = (
        sb.table("vital_treatment_events")
        .select("session_no,scheduled_at,label,status,note")
        .order("session_no")
        .execute()
    )
    rows = r.data or []
    done = sum(1 for x in rows if x.get("status") == "done")
    print(f"sessions={len(rows)} done={done}/{PLANNED_TOTAL_DEFAULT}")
    for x in rows:
        at = x.get("scheduled_at") or "—"
        note = (x.get("note") or "")[:60]
        print(
            f"  #{x['session_no']:02d} {status_ja(x['status']):12s}  "
            f"{at}  {x.get('label')}  {note}"
        )
    return 0


def upsert(
    sb,
    *,
    session_no: int,
    status: str,
    at: str | None,
    note: str | None,
    label: str | None,
) -> int:
    row = {
        "session_no": session_no,
        "label": label or label_for(session_no),
        "status": status,
        "scheduled_at": at,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    if note is not None:
        row["note"] = note
    sb.table("vital_treatment_events").upsert(
        row, on_conflict="session_no"
    ).execute()
    print(f"ok session={session_no} status={status} at={at or 'null'}")
    return 0


def ensure_planned_slots(sb, total: int) -> int:
    existing = (
        sb.table("vital_treatment_events")
        .select("session_no,status")
        .execute()
        .data
        or []
    )
    have = {int(x["session_no"]) for x in existing}
    for n in range(1, total + 1):
        if n in have:
            continue
        upsert(
            sb,
            session_no=n,
            status="planned",
            at=None,
            note="枠（日程未定）。診察後に Jarvis へ伝えて更新。",
            label=label_for(n),
        )
    print(f"ensured planned slots 1..{total}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Quiet Edge treatment schedule")
    p.add_argument("--list", action="store_true")
    p.add_argument("--done", type=int, metavar="N", help="第N回を完了にする")
    p.add_argument("--schedule", type=int, metavar="N", help="第N回の日程を設定（予定）")
    p.add_argument("--plan", type=int, metavar="N", help="第N回を枠（日程未定）にする")
    p.add_argument("--at", help="日時 YYYY-MM-DD or YYYY-MM-DDTHH:MM（JST）")
    p.add_argument("--note", default=None)
    p.add_argument("--label", default=None)
    p.add_argument(
        "--ensure-slots",
        type=int,
        metavar="TOTAL",
        help=f"1..TOTAL の枠を用意（既定の総回数目安={PLANNED_TOTAL_DEFAULT}）",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.dry_run and not args.list:
        print("dry-run:", vars(args))
        return 0

    sb = client()

    if args.list:
        return cmd_list(sb)
    if args.ensure_slots:
        return ensure_planned_slots(sb, args.ensure_slots)
    if args.done is not None:
        at = parse_at(args.at)
        if not at:
            raise SystemExit("--done には --at が必要です")
        return upsert(
            sb,
            session_no=args.done,
            status="done",
            at=at,
            note=args.note,
            label=args.label,
        )
    if args.schedule is not None:
        at = parse_at(args.at)
        if not at:
            raise SystemExit("--schedule には --at が必要です")
        return upsert(
            sb,
            session_no=args.schedule,
            status="scheduled",
            at=at,
            note=args.note,
            label=args.label,
        )
    if args.plan is not None:
        return upsert(
            sb,
            session_no=args.plan,
            status="planned",
            at=None,
            note=args.note or "枠（日程未定）",
            label=args.label,
        )

    p.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
