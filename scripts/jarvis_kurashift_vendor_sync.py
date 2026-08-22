#!/usr/bin/env python3
"""地場業者リスト YAML → kurashift_re_vendors 投影（Mac 正本 → Supabase）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_sync.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_vendor_list import load_list  # noqa: E402


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
    if not s:
        return None
    if len(s) >= 10:
        return s[:10]
    return s


def vendor_row(v: dict[str, Any], *, synced_at: str) -> dict[str, Any]:
    return {
        "id": str(v["id"]),
        "name": str(v.get("name") or "").strip() or str(v["id"]),
        "area": v.get("area") or None,
        "prefecture": v.get("prefecture") or None,
        "city": v.get("city") or None,
        "url": v.get("url") or None,
        "contact_url": v.get("contact_url") or None,
        "channel": str(v.get("channel") or "web_form"),
        "contact_email": v.get("contact_email") or None,
        "phone": v.get("phone") or None,
        "status": str(v.get("status") or "pending"),
        "source": v.get("source") or None,
        "discovered_at": _parse_date(v.get("discovered_at")),
        "contacted_at": _parse_date(v.get("contacted_at")),
        "replied_at": _parse_date(v.get("replied_at")),
        "ops_contacted_at": _parse_date(v.get("ops_contacted_at")),
        "last_result": (str(v.get("last_result") or "")[:500] or None),
        "notes": (str(v.get("notes") or "")[:1000] or None),
        "synced_at": synced_at,
        "updated_at": synced_at,
    }


def sync_vendors(*, apply: bool) -> dict[str, Any]:
    data = load_list()
    vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict) and v.get("id")]
    synced_at = now_iso()
    rows = [vendor_row(v, synced_at=synced_at) for v in vendors]
    settings = data.get("settings") or {}
    counts: dict[str, int] = {}
    for r in rows:
        st = r["status"]
        counts[st] = counts.get(st, 0) + 1

    out: dict[str, Any] = {
        "ok": True,
        "total": len(rows),
        "by_status": counts,
        "yaml_exists": (REPO / "config" / "kurashift_re_vendor_list.yaml").is_file(),
        "daily_outreach_limit": settings.get("daily_outreach_limit", 3),
        "dry_run": not apply,
    }

    if not apply:
        print(f"# vendor_sync dry-run: {len(rows)} rows")
        print(
            "KURASHIFT_RESULT:"
            + json.dumps({**out, "upserted": 0}, ensure_ascii=False)
        )
        return out

    sb = sb_client()
    upserted = 0
    chunk = 50
    for i in range(0, len(rows), chunk):
        batch = rows[i : i + chunk]
        sb.table("kurashift_re_vendors").upsert(batch, on_conflict="id").execute()
        upserted += len(batch)

    out["upserted"] = upserted
    out["synced_at"] = synced_at
    print(
        f"📎 vendor_sync: upserted={upserted} "
        f"pending={counts.get('pending', 0)} contacted={counts.get('contacted', 0)} "
        f"replied={counts.get('replied', 0)}"
    )
    print("KURASHIFT_RESULT:" + json.dumps(out, ensure_ascii=False))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Supabase へ upsert")
    ap.add_argument("--dry-run", action="store_true", help="件数のみ")
    args = ap.parse_args()
    apply = bool(args.apply) and not args.dry_run
    sync_vendors(apply=apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
