#!/usr/bin/env python3
"""S4 修繕業者 YAML → kurashift_re_repair_vendors 投影。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_repair_vendor_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_repair_vendor_sync.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_repair_vendor_list import LIST_PATH, load_list  # noqa: E402
from jarvis_vendor_alive_lib import alive_db_fields, ensure_alive_fields  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def _parse_date(val: Any) -> str | None:
    if not val:
        return None
    s = str(val).strip()
    return s[:10] if s else None


def vendor_row(v: dict[str, Any], *, synced_at: str) -> dict[str, Any]:
    ensure_alive_fields(v, kind="repair")
    row = {
        "id": str(v["id"]),
        "name": str(v.get("name") or "").strip() or str(v["id"]),
        "trade": v.get("trade") or None,
        "area": v.get("area") or None,
        "prefecture": v.get("prefecture") or None,
        "city": v.get("city") or None,
        "url": v.get("url") or None,
        "contact_url": v.get("contact_url") or None,
        "channel": str(v.get("channel") or "phone"),
        "contact_email": v.get("contact_email") or None,
        "phone": v.get("phone") or None,
        "status": str(v.get("status") or "pending"),
        "source": v.get("source") or None,
        "sole_proprietor_score": v.get("sole_proprietor_score") or None,
        "discovered_at": _parse_date(v.get("discovered_at")),
        "contacted_at": _parse_date(v.get("contacted_at")),
        "replied_at": _parse_date(v.get("replied_at")),
        "last_result": (str(v.get("last_result") or "")[:500] or None),
        "notes": (str(v.get("notes") or "")[:1000] or None),
        "synced_at": synced_at,
        "updated_at": synced_at,
    }
    row.update(alive_db_fields(v, kind="repair"))
    return row


def sync_vendors(*, apply: bool) -> dict[str, Any]:
    data = load_list()
    vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict) and v.get("id")]
    synced_at = now_iso()
    rows = [vendor_row(v, synced_at=synced_at) for v in vendors]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    out: dict[str, Any] = {
        "ok": True,
        "total": len(rows),
        "by_status": counts,
        "yaml_exists": LIST_PATH.is_file(),
        "dry_run": not apply,
    }
    if not apply:
        print(f"# repair_vendor_sync dry-run: {len(rows)} rows")
        print("KURASHIFT_RESULT:" + json.dumps({**out, "upserted": 0}, ensure_ascii=False))
        return out
    sb = sb_client()
    upserted = 0
    for i in range(0, len(rows), 50):
        batch = rows[i : i + 50]
        sb.table("kurashift_re_repair_vendors").upsert(batch, on_conflict="id").execute()
        upserted += len(batch)
    out["upserted"] = upserted
    out["synced_at"] = synced_at
    print(f"📎 repair_vendor_sync: upserted={upserted}")
    print("KURASHIFT_RESULT:" + json.dumps(out, ensure_ascii=False))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    apply = bool(args.apply) and not args.dry_run
    sync_vendors(apply=apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
