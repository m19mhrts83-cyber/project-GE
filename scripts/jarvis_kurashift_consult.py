#!/usr/bin/env python3
"""Record a local Jarvis consultation into kurashift_consultations for the app."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--body", required=True)
    ap.add_argument(
        "--lane",
        default="general",
        choices=["general", "lifeplan", "theme", "tax", "core"],
    )
    ap.add_argument("--decision", default="")
    ap.add_argument("--status", default="open", choices=["open", "decided", "archived"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    row = {
        "title": args.title,
        "body": args.body,
        "lane": args.lane,
        "decision": args.decision or None,
        "status": args.status if not args.decision else "decided",
        "updated_at": now_iso(),
    }
    print(json.dumps(row, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY required")
    from supabase import create_client

    sb = create_client(url, key)
    res = sb.table("kurashift_consultations").insert(row).execute()
    print("KURASHIFT_RESULT:" + json.dumps({"id": (res.data or [{}])[0].get("id")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
