#!/usr/bin/env python3
"""Supabase cards の status=active を一括 archived。

  python scripts/jarvis_lane_cards_archive_active.py --dry-run
  python scripts/jarvis_lane_cards_archive_active.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_lane_log import LANE_META, append_lane_log, ensure_lane_log_tree  # noqa: E402


def load_env() -> None:
    env_path = REPO / ".env.jarvis_private"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("\"'")
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--lanes",
        default=",".join(LANE_META.keys()),
        help="comma-separated lane ids",
    )
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply", file=sys.stderr)
        return 2

    load_env()
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)

    lanes = [x.strip() for x in args.lanes.split(",") if x.strip()]
    r = (
        sb.table("cards")
        .select("id,lane,title,status")
        .eq("status", "active")
        .execute()
    )
    rows = [x for x in (r.data or []) if x.get("lane") in lanes]
    counts = Counter(x.get("lane") or "?" for x in rows)
    print(f"# active to archive: {len(rows)}")
    for lid in lanes:
        print(f"  {lid}: {counts.get(lid, 0)}")

    if args.dry_run or not rows:
        return 0

    now = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")
    ids = [x["id"] for x in rows]
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        sb.table("cards").update(
            {"status": "archived", "archived_at": now, "updated_at": now}
        ).in_("id", chunk).execute()

    ensure_lane_log_tree(lanes)
    for lid in lanes:
        n = counts.get(lid, 0)
        if n:
            append_lane_log(
                lid,
                "一括アーカイブ",
                f"- active {n} 件を archived（要約確認フローやり直し）",
            )
    print(f"# archived {len(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
