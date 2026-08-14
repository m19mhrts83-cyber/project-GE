#!/usr/bin/env python3
"""号室の家賃条件を手動セット（Jarvis 経路）。ダッシュボード「条件を修正」と同正本。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_property_unit_set.py --unit grandole-ii-205 \\
    --rent 47000 --mgmt 4000 --rent-year1 47000 --rent-year2 51000 \\
    --status occupied --reason '成約条件に合わせて修正'
  python scripts/jarvis_property_unit_set.py --property II --room 205 \\
    --rent-year1 45000 --reason 'キャンペーン反映'
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


def parse_yen(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).replace(",", "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError as e:
        raise SystemExit(f"金額が不正です: {raw}") from e


def fmt(n: float | None) -> str:
    if n is None:
        return "—"
    return f"{int(round(n)):,}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="号室条件の手動セット")
    ap.add_argument("--unit", help="例: grandole-ii-205")
    ap.add_argument("--property", help="I / II / C または property_id")
    ap.add_argument("--room", help="例: 205")
    ap.add_argument("--rent", help="現状家賃")
    ap.add_argument("--mgmt", "--management-fee", dest="mgmt", help="管理費")
    ap.add_argument("--rent-year1", dest="rent_year1", help="1年目家賃")
    ap.add_argument("--rent-year2", dest="rent_year2", help="2年目（計画）家賃")
    ap.add_argument("--campaign-until", dest="campaign_until", help="キャンペーン期限")
    ap.add_argument(
        "--status",
        choices=["occupied", "vacant"],
        help="入居 / 空室",
    )
    ap.add_argument("--reason", default="", help="修正理由（memo_log に残る）")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="DB に書かず差分だけ表示",
    )
    args = ap.parse_args(argv)

    fields_set = any(
        [
            args.rent is not None,
            args.mgmt is not None,
            args.rent_year1 is not None,
            args.rent_year2 is not None,
            args.campaign_until is not None,
            args.status is not None,
        ]
    )
    if not fields_set:
        raise SystemExit(
            "少なくとも1つ指定: --rent / --mgmt / --rent-year1 / --rent-year2 / "
            "--campaign-until / --status"
        )

    unit_id = resolve_unit_id(args)
    sb = sb_client()
    res = (
        sb.table("property_units")
        .select("id,rent,status,note,payload")
        .eq("id", unit_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise SystemExit(f"unit not found: {unit_id}")
    row = rows[0]
    payload: dict[str, Any] = dict(row.get("payload") or {})

    prev_rent = float(row["rent"]) if row.get("rent") is not None else None
    prev_mgmt = payload.get("management_fee")
    if prev_mgmt is None:
        prev_mgmt = payload.get("mgmt_fee")
    prev_mgmt = float(prev_mgmt) if prev_mgmt is not None else None
    prev_y1 = (
        float(payload["rent_year1"]) if payload.get("rent_year1") is not None else None
    )
    prev_y2 = (
        float(payload["rent_year2"]) if payload.get("rent_year2") is not None else None
    )

    next_rent = parse_yen(args.rent) if args.rent is not None else prev_rent
    next_mgmt = parse_yen(args.mgmt) if args.mgmt is not None else prev_mgmt
    next_y1 = parse_yen(args.rent_year1) if args.rent_year1 is not None else prev_y1
    next_y2 = parse_yen(args.rent_year2) if args.rent_year2 is not None else prev_y2
    next_status = args.status or row.get("status") or "occupied"
    campaign_until = (
        str(args.campaign_until).strip()
        if args.campaign_until is not None
        else str(payload.get("campaign_until") or "")
    )

    if next_mgmt is not None:
        payload["management_fee"] = next_mgmt
        payload["mgmt_fee"] = next_mgmt
    if next_y1 is not None:
        payload["rent_year1"] = next_y1
    if next_y2 is not None:
        payload["rent_year2"] = next_y2
    if next_rent is not None:
        payload["total_rent"] = float(next_rent) + (
            float(next_mgmt) if next_mgmt is not None else 0.0
        )
    if next_y1 is not None:
        payload["total_year1"] = float(next_y1) + (
            float(next_mgmt) if next_mgmt is not None else 0.0
        )
    if next_y2 is not None:
        payload["total_year2"] = float(next_y2) + (
            float(next_mgmt) if next_mgmt is not None else 0.0
        )
    if next_y1 is not None and next_y2 is not None and float(next_y2) > float(next_y1):
        disc = float(next_y2) - float(next_y1)
        payload["discount_yen"] = disc
        payload["discount_rate"] = round(100.0 * disc / float(next_y2), 1)
    if args.campaign_until is not None:
        if campaign_until:
            payload["campaign_until"] = campaign_until[:40]
        else:
            payload.pop("campaign_until", None)

    changes: list[str] = []
    if prev_rent != next_rent:
        changes.append(f"現状家賃 {fmt(prev_rent)}→{fmt(next_rent)}")
    if prev_mgmt != next_mgmt:
        changes.append(f"管理費 {fmt(prev_mgmt)}→{fmt(next_mgmt)}")
    if prev_y1 != next_y1:
        changes.append(f"1年目 {fmt(prev_y1)}→{fmt(next_y1)}")
    if prev_y2 != next_y2:
        changes.append(f"2年目 {fmt(prev_y2)}→{fmt(next_y2)}")
    if next_status != row.get("status"):
        changes.append(
            f"状態 {'空室' if row.get('status')=='vacant' else '入居'}→"
            f"{'空室' if next_status=='vacant' else '入居'}"
        )
    if args.campaign_until is not None and campaign_until:
        changes.append(f"期限 {campaign_until}")

    reason = str(args.reason or "").strip()
    memo = " · ".join(
        [
            "条件修正",
            " / ".join(changes) if changes else "（値変更なし）",
            f"理由: {reason}" if reason else "",
        ]
    ).strip(" ·")[:400]

    now = datetime.now(tz=JST).isoformat()
    log = list(payload.get("memo_log") or [])
    if not isinstance(log, list):
        log = []
    log.append({"at": now, "text": memo, "source": "jarvis"})
    payload["memo_log"] = log[-80:]

    print(f"# {unit_id}")
    for c in changes or ["（変更なし）"]:
        print(f"  - {c}")
    print(f"  memo: {memo}")

    if args.dry_run:
        print("# dry-run (not written)")
        return 0

    update: dict[str, Any] = {
        "rent": next_rent,
        "status": next_status,
        "note": memo[:500],
        "payload": payload,
        "updated_at": now,
        "source": "jarvis",
    }
    sb.table("property_units").update(update).eq("id", unit_id).execute()
    print(f"# ok {unit_id} terms updated source=jarvis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
