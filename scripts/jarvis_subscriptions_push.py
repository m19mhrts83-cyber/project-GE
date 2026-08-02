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
SNAP_DIR = REPO / ".jarvis_state" / "subscriptions_snapshots"
BILLING_STATE = REPO / ".jarvis_state" / "billing_monthly.json"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def ym_now() -> str:
    return datetime.now(JST).strftime("%Y-%m")


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


def _svc_index(services: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for s in services:
        sid = str(s.get("id") or "").strip()
        if sid:
            out[sid] = s
    return out


def compute_diff(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]] | None,
    *,
    ym: str,
    prev_ym: str | None,
) -> dict[str, Any]:
    cur = _svc_index(current)
    prev = _svc_index(previous or [])
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    amount_changed: list[dict[str, Any]] = []
    status_changed: list[dict[str, Any]] = []
    watch_alerts: list[dict[str, Any]] = []

    for sid, s in cur.items():
        if sid not in prev:
            added.append(
                {
                    "id": sid,
                    "name": s.get("name"),
                    "monthly_yen": s.get("monthly_yen"),
                    "status": s.get("status"),
                }
            )
            watch_alerts.append(
                {
                    "id": sid,
                    "name": s.get("name"),
                    "reason": "新規追加",
                    "watch": bool(s.get("watch")),
                }
            )
            continue
        p = prev[sid]
        if float(s.get("amount_yen") or 0) != float(p.get("amount_yen") or 0) or float(
            s.get("monthly_yen") or 0
        ) != float(p.get("monthly_yen") or 0):
            amount_changed.append(
                {
                    "id": sid,
                    "name": s.get("name"),
                    "from_amount": p.get("amount_yen"),
                    "to_amount": s.get("amount_yen"),
                    "from_monthly": p.get("monthly_yen"),
                    "to_monthly": s.get("monthly_yen"),
                }
            )
        if str(s.get("status") or "") != str(p.get("status") or ""):
            status_changed.append(
                {
                    "id": sid,
                    "name": s.get("name"),
                    "from": p.get("status"),
                    "to": s.get("status"),
                }
            )
        if bool(s.get("watch")) and not bool(p.get("watch")):
            watch_alerts.append(
                {
                    "id": sid,
                    "name": s.get("name"),
                    "reason": s.get("watch_reason") or "注視オン",
                    "watch": True,
                }
            )

    for sid, p in prev.items():
        if sid not in cur:
            removed.append(
                {
                    "id": sid,
                    "name": p.get("name"),
                    "monthly_yen": p.get("monthly_yen"),
                    "status": p.get("status"),
                }
            )

    # 新規・注視オン変化のみ（継続ウォッチは watch_active 側）
    watch_new_or_flagged = list(watch_alerts)
    watch_active = [
        {
            "id": s["id"],
            "name": s.get("name"),
            "reason": s.get("watch_reason") or "watch",
        }
        for s in current
        if s.get("watch")
    ]

    cur_total = round(
        sum(float(s.get("monthly_yen") or 0) for s in current if s.get("status") == "active"),
        2,
    )
    prev_total = round(
        sum(
            float(s.get("monthly_yen") or 0)
            for s in (previous or [])
            if s.get("status") == "active"
        ),
        2,
    )
    return {
        "as_of_ym": ym,
        "prev_ym": prev_ym,
        "compared_at": now_iso(),
        "active_monthly_total": cur_total,
        "prev_active_monthly_total": prev_total if previous is not None else None,
        "delta_monthly": round(cur_total - prev_total, 2) if previous is not None else None,
        "added": added,
        "removed": removed,
        "amount_changed": amount_changed,
        "status_changed": status_changed,
        "watch_alerts": watch_new_or_flagged,
        "watch_active": watch_active,
        "has_changes": bool(
            added or removed or amount_changed or status_changed or watch_new_or_flagged
        )
        if previous is not None
        else bool(added or watch_active),
        "confirmed_at": None,
    }


def load_snapshot(ym: str) -> dict[str, Any] | None:
    path = SNAP_DIR / f"{ym}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_snapshot(ym: str, rows: list[dict[str, Any]], summary: dict[str, Any]) -> Path:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / f"{ym}.json"
    payload = {
        "ym": ym,
        "saved_at": now_iso(),
        "summary": summary,
        "services": [
            {
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "status": r["status"],
                "billing": r["billing"],
                "amount_yen": r["amount_yen"],
                "monthly_yen": r["monthly_yen"],
                "watch": r["watch"],
                "watch_reason": r.get("watch_reason"),
            }
            for r in rows
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def previous_ym(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def build_and_store_monthly_summary(
    rows: list[dict[str, Any]], summary: dict[str, Any]
) -> dict[str, Any]:
    ym = ym_now()
    save_snapshot(ym, rows, summary)
    prev = previous_ym(ym)
    prev_snap = load_snapshot(prev)
    # 前月が無ければ直近の別月スナップを探す
    prev_services = None
    prev_label: str | None = prev
    if prev_snap:
        prev_services = prev_snap.get("services") or []
    else:
        snaps = sorted(SNAP_DIR.glob("*.json"), reverse=True)
        for p in snaps:
            if p.stem == ym:
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            prev_services = data.get("services") or []
            prev_label = data.get("ym") or p.stem
            break
        else:
            prev_label = None

    diff = compute_diff(rows, prev_services, ym=ym, prev_ym=prev_label)
    # 既存 confirmed_at を維持
    if BILLING_STATE.is_file():
        try:
            old = json.loads(BILLING_STATE.read_text(encoding="utf-8"))
            if old.get("as_of_ym") == ym and old.get("confirmed_at"):
                diff["confirmed_at"] = old.get("confirmed_at")
        except Exception:
            pass
    BILLING_STATE.parent.mkdir(parents=True, exist_ok=True)
    BILLING_STATE.write_text(
        json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return diff


def push_supabase(rows: list[dict[str, Any]], monthly: dict[str, Any] | None = None) -> int:
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
    if monthly is not None:
        sb.table("sync_meta").upsert(
            {
                "key": "subscriptions_monthly_summary",
                "value": json.dumps(monthly, ensure_ascii=False),
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
    monthly = build_and_store_monthly_summary(rows, summary)
    print(
        f"# subscriptions={summary['count']} "
        f"active_monthly={summary['active_monthly_total']:,.0f} "
        f"ai={summary['ai_monthly']:,.0f} other={summary['other_monthly']:,.0f} "
        f"watch={summary['watch_count']}",
        file=sys.stderr,
    )
    delta = monthly.get("delta_monthly")
    print(
        f"# monthly_summary ym={monthly.get('as_of_ym')} "
        f"prev={monthly.get('prev_ym')} delta={delta} "
        f"added={len(monthly.get('added') or [])} "
        f"changed={len(monthly.get('amount_changed') or [])}",
        file=sys.stderr,
    )
    if args.dry_run:
        print(json.dumps({"summary": summary, "monthly": monthly}, ensure_ascii=False, indent=2))
        return 0
    if args.push:
        n = push_supabase(rows, monthly)
        print(f"# pushed {n}", file=sys.stderr)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
