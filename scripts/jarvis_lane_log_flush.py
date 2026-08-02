#!/usr/bin/env python3
"""Supabase lane_action_log → レーン別 5.処置ログ.md へフラッシュ。

  python scripts/jarvis_lane_log_flush.py
  python scripts/jarvis_lane_log_flush.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_lane_log import append_lane_log, ensure_lane_log_tree  # noqa: E402


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
    args = ap.parse_args()
    load_env()
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)

    r = (
        sb.table("lane_action_log")
        .select("id,lane,event,body,card_id,created_at")
        .is_("flushed_at", "null")
        .order("created_at", desc=False)
        .limit(500)
        .execute()
    )
    rows = r.data or []
    print(f"# pending {len(rows)}")
    if args.dry_run or not rows:
        return 0

    ensure_lane_log_tree(sorted({x["lane"] for x in rows}))
    now = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")
    for row in rows:
        body = row.get("body") or ""
        cid = row.get("card_id")
        if cid:
            body = f"{body.rstrip()}\n- card_id: `{cid}`"
        append_lane_log(row["lane"], str(row.get("event") or "操作"), body)
        sb.table("lane_action_log").update({"flushed_at": now}).eq(
            "id", row["id"]
        ).execute()
    print(f"# flushed {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
