#!/usr/bin/env python3
"""
Jarvis: config/subscriptions.yaml → ローカル JSON ＋任意で Supabase subscription_services。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_subscriptions_push.py --dry-run
  python scripts/jarvis_subscriptions_push.py --push
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
CFG_PATH = REPO / "config" / "subscriptions.yaml"
OUT_PATH = REPO / ".jarvis_state" / "subscriptions.json"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def monthly_yen(billing: str, amount: float) -> float:
    b = (billing or "none").lower()
    if b == "yearly":
        return round(amount / 12.0, 2)
    if b in ("monthly", "usage"):
        return float(amount)
    return float(amount) if amount else 0.0


def load_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}
    services = raw.get("services") or []
    rows: list[dict[str, Any]] = []
    for s in services:
        sid = str(s.get("id") or "").strip()
        if not sid:
            continue
        amount = float(s.get("amount_yen") or 0)
        billing = str(s.get("billing") or "none")
        status = str(s.get("status") or "unknown")
        m = monthly_yen(billing, amount)
        # 継続のみ月額換算をサマリーに使う（free/ended は 0 扱いでも DB には格納）
        if status not in ("active", "ending") or status == "ending" and amount <= 0:
            if status in ("ended", "free", "unknown"):
                m = 0.0 if status != "active" else m
        if status in ("ended", "free"):
            m = 0.0
        if status == "ending" and amount <= 0:
            m = 0.0
        rows.append(
            {
                "id": sid,
                "name": str(s.get("name") or sid),
                "category": str(s.get("category") or "lifestyle"),
                "status": status,
                "billing": billing,
                "amount_yen": amount,
                "monthly_yen": m,
                "next_bill": (str(s.get("next_bill") or "").strip() or None),
                "watch": bool(s.get("watch")),
                "watch_reason": (str(s.get("watch_reason") or "").strip() or None),
                "usage_note": (str(s.get("usage_note") or "").strip() or None),
                "cancel_candidate": bool(s.get("cancel_candidate")),
                "billing_url": (str(s.get("billing_url") or "").strip() or None),
                "note": (str(s.get("note") or "").strip() or None),
                "updated_at": now_iso(),
            }
        )
    summary = {
        "as_of": raw.get("as_of"),
        "count": len(rows),
        "active_monthly_total": round(
            sum(r["monthly_yen"] for r in rows if r["status"] == "active"), 2
        ),
        "ai_monthly": round(
            sum(
                r["monthly_yen"]
                for r in rows
                if r["status"] == "active" and r["category"] == "ai"
            ),
            2,
        ),
        "other_monthly": round(
            sum(
                r["monthly_yen"]
                for r in rows
                if r["status"] == "active" and r["category"] != "ai"
            ),
            2,
        ),
        "watch_count": sum(1 for r in rows if r["watch"]),
    }
    return rows, summary


def push_supabase(rows: list[dict[str, Any]]) -> int:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit(
            "JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定です"
        )
    sb = create_client(url, key)
    # DB 列に無い note は payload 相当にしない（schema に note を含める）
    n = 0
    for i in range(0, len(rows), 50):
        chunk = rows[i : i + 50]
        sb.table("subscription_services").upsert(chunk, on_conflict="id").execute()
        n += len(chunk)
    sb.table("sync_meta").upsert(
        {
            "key": "subscriptions_pushed_at",
            "value": now_iso(),
            "updated_at": now_iso(),
        },
        on_conflict="key",
    ).execute()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not CFG_PATH.is_file():
        print(f"# missing {CFG_PATH}", file=sys.stderr)
        return 1

    rows, summary = load_rows()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "services": rows}
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"# subscriptions={summary['count']} "
        f"active_monthly={summary['active_monthly_total']:,.0f} "
        f"ai={summary['ai_monthly']:,.0f} other={summary['other_monthly']:,.0f} "
        f"watch={summary['watch_count']}",
        file=sys.stderr,
    )
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if args.push:
        n = push_supabase(rows)
        print(f"# pushed {n}", file=sys.stderr)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
