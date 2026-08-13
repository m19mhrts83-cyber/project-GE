#!/usr/bin/env python3
"""号室メモ追記（Jarvis 経路）。ダッシュボード UI と同じ property_units.payload.memo_log。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_property_unit_memo.py --unit grandole-ii-205 --text '内覧予定 8/20'
  python scripts/jarvis_property_unit_memo.py --property II --room 205 --text '...'
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

SHORT_TO_PROPERTY = {
    "I": "grandole-i",
    "II": "grandole-ii",
    "C": "caramel",
    "grandole-i": "grandole-i",
    "grandole-ii": "grandole-ii",
    "caramel": "caramel",
}


def sb_client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    return create_client(url, key)


def resolve_unit_id(args: argparse.Namespace) -> str:
    if args.unit:
        return str(args.unit).strip()
    prop = SHORT_TO_PROPERTY.get(str(args.property or "").strip())
    room = str(args.room or "").strip()
    if not prop or not room:
        raise SystemExit("--unit か --property + --room が必要です")
    return f"{prop}-{room}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", help="例: grandole-ii-205")
    ap.add_argument("--property", help="I / II / C または property_id")
    ap.add_argument("--room", help="例: 205")
    ap.add_argument("--text", required=True)
    args = ap.parse_args(argv)

    text = str(args.text or "").strip()
    if not text:
        raise SystemExit("text が空です")
    unit_id = resolve_unit_id(args)
    sb = sb_client()
    res = (
        sb.table("property_units")
        .select("id,note,payload")
        .eq("id", unit_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise SystemExit(f"unit not found: {unit_id}")
    row = rows[0]
    payload: dict[str, Any] = dict(row.get("payload") or {})
    log = list(payload.get("memo_log") or [])
    if not isinstance(log, list):
        log = []
    now = datetime.now(tz=JST).isoformat()
    log.append({"at": now, "text": text[:400], "source": "jarvis"})
    payload["memo_log"] = log[-80:]
    note = text[:500]
    sb.table("property_units").update(
        {"note": note, "payload": payload, "updated_at": now}
    ).eq("id", unit_id).execute()
    print(f"# ok {unit_id} memo appended source=jarvis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
