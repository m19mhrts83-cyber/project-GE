#!/usr/bin/env python3
"""
Web ダッシュボードから送信済みの **地場業者返信**（payload.re_vendor_reply）を
YAML 業者リストへ反映する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_triage_vendor_catchup.py
  ~/selenium_env/venv/bin/python scripts/jarvis_triage_vendor_catchup.py --dry-run

夜間トリアージ後・morning_mac_refresh から呼ぶ。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_vendor_list import load_list, save_list, vendor_index  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sync sent vendor replies to YAML")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args(argv)

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return 1

    from supabase import create_client

    sb = create_client(url, key)
    r = (
        sb.table("triage_items")
        .select("id,status,payload,updated_at")
        .eq("status", "sent")
        .order("updated_at", desc=True)
        .limit(args.limit)
        .execute()
    )
    rows = r.data or []
    data = load_list()
    idx = vendor_index(data)
    done = 0
    skipped = 0

    for it in rows:
        payload = it.get("payload") if isinstance(it.get("payload"), dict) else {}
        if not payload.get("re_vendor_reply"):
            continue
        if payload.get("vendor_yaml_synced"):
            skipped += 1
            continue
        vid = str(payload.get("vendor_id") or "").strip()
        if not vid or vid not in idx:
            print(f"# skip unknown vendor id={vid} triage={it.get('id')}", file=sys.stderr)
            continue
        v = idx[vid]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        note = f"estate返信送信 {today}"
        print(f"# vendor catchup {vid} {v.get('name')}")
        if not args.dry_run:
            v["status"] = "replied"
            if not (v.get("replied_at") or "").strip():
                v["replied_at"] = today
            prev = (v.get("notes") or "").strip()
            v["notes"] = f"{prev} | {note}".strip(" |") if prev else note
            payload = dict(payload)
            payload["vendor_yaml_synced"] = True
            payload["vendor_yaml_synced_at"] = now_iso()
            sb.table("triage_items").update(
                {"payload": payload, "updated_at": now_iso()}
            ).eq("id", it["id"]).execute()
        done += 1

    if done and not args.dry_run:
        save_list(data)

    print(f"# vendor_catchup synced={done} already={skipped} scanned={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
