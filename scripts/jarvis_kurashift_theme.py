#!/usr/bin/env python3
"""Theme card helpers for KURASHIFT (preview only; no live trades)."""
from __future__ import annotations

import argparse
import json
import os


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--theme-id", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.preview:
        raise SystemExit("only --preview is supported in this phase")

    out = {
        "action": "theme_preview",
        "theme_id": args.theme_id,
        "note": "提案プレビューのみ。実弾・振替は承認ジョブが別途必要。",
        "live": False,
    }

    if args.theme_id and not args.dry_run:
        url = os.environ.get("JARVIS_SUPABASE_URL")
        key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            from supabase import create_client

            sb = create_client(url, key)
            row = (
                sb.table("kurashift_themes")
                .select("*")
                .eq("id", args.theme_id)
                .maybe_single()
                .execute()
                .data
            )
            out["theme"] = row

    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("KURASHIFT_RESULT:" + json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
