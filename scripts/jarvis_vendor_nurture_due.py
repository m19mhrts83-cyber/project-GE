#!/usr/bin/env python3
"""業者開拓・定期情報確認（nurture）due 抽出。

Phase1: YAML を読み、最終アウトバウンドから interval_days 以上の社を列挙。
--apply で .jarvis_state/vendor_nurture_due.json に書く（送信しない）。

正本: docs/KURASHIFT_業者開拓_定期情報確認_20261019.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
STATE_PATH = STATE_DIR / "vendor_nurture_due.json"
DEFAULT_CFG = REPO / "config" / "kurashift_vendor_nurture.yaml"


def _today() -> date:
    return datetime.now().astimezone().date()


def _parse_day(raw: Any) -> date | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _last_outbound(v: dict[str, Any]) -> date | None:
    days = [
        _parse_day(v.get("contacted_at")),
        _parse_day(v.get("nurture_last_sent_at")),
    ]
    days = [d for d in days if d]
    return max(days) if days else None


def _eligible(v: dict[str, Any], *, include: set[str], exclude: set[str]) -> bool:
    st = str(v.get("status") or "pending").strip()
    if st in exclude:
        return False
    if _parse_day(v.get("contacted_at")):
        return True
    return st in include


def collect_due(
    *,
    list_path: Path,
    interval_days: int,
    include_statuses: list[str],
    exclude_statuses: list[str],
    as_of: date | None = None,
) -> dict[str, Any]:
    as_of = as_of or _today()
    data = _load_yaml(list_path)
    vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict) and v.get("id")]
    include = {str(s) for s in include_statuses}
    exclude = {str(s) for s in exclude_statuses}
    threshold = as_of - timedelta(days=interval_days)

    due: list[dict[str, Any]] = []
    skipped = 0
    for v in vendors:
        if not _eligible(v, include=include, exclude=exclude):
            skipped += 1
            continue
        last = _last_outbound(v)
        if last is None:
            skipped += 1
            continue
        if last > threshold:
            continue
        gap = (as_of - last).days
        due.append(
            {
                "id": str(v["id"]),
                "name": str(v.get("name") or v["id"]),
                "status": str(v.get("status") or ""),
                "contacted_at": str(v.get("contacted_at") or "")[:10],
                "nurture_last_sent_at": str(v.get("nurture_last_sent_at") or "")[:10],
                "nurture_last_reply": str(v.get("nurture_last_reply") or "none"),
                "nurture_last_reply_at": str(v.get("nurture_last_reply_at") or "")[:10],
                "last_outbound": last.isoformat(),
                "gap_days": gap,
                "contact_email": str(v.get("contact_email") or ""),
                "channel": str(v.get("channel") or ""),
            }
        )

    due.sort(key=lambda r: (-int(r["gap_days"]), str(r["id"])))
    return {
        "as_of": as_of.isoformat(),
        "interval_days": interval_days,
        "list_path": str(list_path),
        "total_vendors": len(vendors),
        "skipped_or_ineligible": skipped,
        "due_count": len(due),
        "due": due,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=DEFAULT_CFG)
    ap.add_argument("--dry-run", action="store_true", help="state に書かず表示のみ")
    ap.add_argument("--apply", action="store_true", help="state に due 一覧を書く（送信しない）")
    ap.add_argument("--limit", type=int, default=20, help="stdout に出す件数")
    args = ap.parse_args()

    if os.environ.get("JARVIS_VENDOR_NURTURE_DISABLE", "").strip() in {"1", "true", "yes"}:
        print("disabled via JARVIS_VENDOR_NURTURE_DISABLE=1")
        return 0

    cfg = _load_yaml(args.config)
    if cfg.get("disabled") is True:
        print("disabled via config disabled: true")
        return 0

    settings = cfg.get("settings") or {}
    interval = int(settings.get("interval_days") or 60)
    rel = str(settings.get("list_yaml") or "config/kurashift_re_vendor_list.yaml")
    list_path = (REPO / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
    include = list(settings.get("include_statuses") or ["contacted", "replied"])
    exclude = list(
        settings.get("exclude_statuses")
        or ["skip", "invalid", "pending", "discovered"]
    )
    daily_limit = int(settings.get("daily_send_limit") or 3)

    if not list_path.is_file():
        print(f"list yaml missing: {list_path}", file=sys.stderr)
        return 2

    result = collect_due(
        list_path=list_path,
        interval_days=interval,
        include_statuses=include,
        exclude_statuses=exclude,
    )
    result["daily_send_limit"] = daily_limit
    result["lane"] = str(settings.get("lane") or "s2")
    result["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

    print(
        f"📎 定期情報確認 due — as_of {result['as_of']} · "
        f"interval {interval}d · due {result['due_count']} / "
        f"vendors {result['total_vendors']} · daily_cap {daily_limit}"
    )
    for row in result["due"][: max(0, args.limit)]:
        print(
            f"- {row['id']}: {row['name'][:40]} · "
            f"last_out {row['last_outbound']} ({row['gap_days']}d) · "
            f"reply={row['nurture_last_reply'] or 'none'}"
        )
    if result["due_count"] > args.limit:
        print(f"  …他 {result['due_count'] - args.limit} 件")

    if args.apply and not args.dry_run:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"# wrote {STATE_PATH}")
    elif args.dry_run or not args.apply:
        print("# dry-run（state 未更新。書くときは --apply）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
