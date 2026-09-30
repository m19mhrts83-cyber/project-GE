#!/usr/bin/env python3
"""S4 修繕業者リスト — 正本 YAML / mark / alive / merge。

正本: config/kurashift_repair_vendor_list.yaml（.gitignore。example から開始）

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_repair_vendor_list.py --summary
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_repair_vendor_list.py --next 5 --alive-ok-first
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_repair_vendor_list.py --mark ID --status contacted
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_repair_vendor_list.py --mark-alive ID --alive-status ok
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_repair_vendor_list.py --alive-queue --limit 2
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_repair_vendor_list.py --merge-append block.yaml
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_vendor_alive_lib import (  # noqa: E402
    build_alive_queue,
    effective_alive_status,
    ensure_alive_fields,
    is_alive_ok,
    mark_alive as mark_alive_fields,
)

LIST_PATH = REPO / "config" / "kurashift_repair_vendor_list.yaml"
EXAMPLE_PATH = REPO / "config" / "kurashift_repair_vendor_list.example.yaml"

STATUSES = frozenset(
    {"pending", "contacted", "replied", "skip", "discovered", "invalid"}
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug_id(name: str, trade: str = "", area: str = "") -> str:
    base = f"repair-{name}-{trade}-{area}".strip().lower()
    base = re.sub(r"\s+", "-", base)
    base = re.sub(r"[^a-z0-9\-ぁ-んァ-ヶ一-龥]", "", base)
    if len(base) >= 8:
        return base[:48]
    h = hashlib.sha256(base.encode()).hexdigest()[:8]
    return f"repair-{h}"


def load_list(path: Path | None = None) -> dict[str, Any]:
    p = path or LIST_PATH
    if not p.is_file():
        if EXAMPLE_PATH.is_file():
            data = yaml.safe_load(EXAMPLE_PATH.read_text(encoding="utf-8")) or {}
            data.setdefault("settings", {})
            data.setdefault("vendors", data.get("vendors") or [])
            # example はトップレベル daily_limit 等あり → settings へ寄せる
            if "daily_limit" in data and "daily_outreach_limit" not in data["settings"]:
                data["settings"]["daily_outreach_limit"] = data.get("daily_limit", 2)
            return data
        return {"settings": {}, "vendors": []}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {
        "settings": {},
        "vendors": [],
    }


def save_list(data: dict[str, Any], path: Path | None = None) -> None:
    p = path or LIST_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def vendor_index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for v in data.get("vendors") or []:
        if isinstance(v, dict) and v.get("id"):
            out[str(v["id"])] = v
    return out


def summary() -> dict[str, Any]:
    data = load_list()
    vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
    counts: dict[str, int] = {}
    alive_ok_n = 0
    by_trade: dict[str, int] = {}
    for v in vendors:
        ensure_alive_fields(v, kind="repair")
        st = str(v.get("status") or "pending")
        counts[st] = counts.get(st, 0) + 1
        tr = str(v.get("trade") or "—")
        by_trade[tr] = by_trade.get(tr, 0) + 1
        if is_alive_ok(v, kind="repair"):
            alive_ok_n += 1
    return {
        "ok": True,
        "total": len(vendors),
        "by_status": counts,
        "by_trade": by_trade,
        "alive_ok": alive_ok_n,
        "yaml_exists": LIST_PATH.is_file(),
        "settings": data.get("settings") or {},
    }


def next_for_contact(
    *,
    limit: int,
    trade: str = "",
    alive_ok_first: bool = True,
) -> list[dict[str, Any]]:
    """修繕依頼候補。alive_ok を先頭に。"""
    data = load_list()
    cand: list[dict[str, Any]] = []
    for v in data.get("vendors") or []:
        if not isinstance(v, dict) or not v.get("id"):
            continue
        st = str(v.get("status") or "pending")
        if st in ("skip", "invalid"):
            continue
        if trade and str(v.get("trade") or "") != trade:
            continue
        ensure_alive_fields(v, kind="repair")
        cand.append(v)

    def sort_key(v: dict[str, Any]) -> tuple:
        ok = is_alive_ok(v, kind="repair")
        # pending/discovered を依頼しやすい順に
        st = str(v.get("status") or "pending")
        st_rank = 0 if st in ("pending", "discovered") else 1
        return (0 if ok else 1, st_rank, str(v.get("id") or ""))

    if alive_ok_first:
        cand.sort(key=sort_key)
    return cand[: max(0, limit)]


def mark_vendor(
    vid: str,
    *,
    status: str,
    note: str = "",
    result: str = "",
    dry_run: bool,
) -> dict[str, Any]:
    if status not in STATUSES:
        return {"ok": False, "error": f"invalid status: {status}"}
    data = load_list()
    by_id = vendor_index(data)
    v = by_id.get(vid)
    if not v:
        return {"ok": False, "error": f"vendor not found: {vid}"}
    today = now_iso()[:10]
    v["status"] = status
    if note:
        v["notes"] = note if not v.get("notes") else f"{v['notes']} | {note}"
    if result:
        v["last_result"] = result
    if status == "contacted":
        v["contacted_at"] = today
    if status == "replied":
        v["replied_at"] = today
    v["updated_at"] = now_iso()
    ensure_alive_fields(v, kind="repair")
    if not dry_run:
        save_list(data)
    return {"ok": True, "vendor": v, "dry_run": dry_run}


def mark_vendor_alive(
    vid: str,
    *,
    alive_status: str,
    method: str = "phone",
    note: str = "",
    dry_run: bool,
) -> dict[str, Any]:
    st = (alive_status or "").strip().lower()
    if st not in ("ok", "fail", "unknown"):
        return {"ok": False, "error": f"invalid alive_status: {alive_status}"}
    data = load_list()
    by_id = vendor_index(data)
    v = by_id.get(vid)
    if not v:
        return {"ok": False, "error": f"vendor not found: {vid}"}
    mark_alive_fields(v, status=st, method=method, note=note, kind="repair")
    if not dry_run:
        save_list(data)
    return {
        "ok": True,
        "vendor": v,
        "alive_effective": effective_alive_status(v, kind="repair"),
        "dry_run": dry_run,
    }


def merge_append(vendors: list[Any], *, dry_run: bool) -> dict[str, Any]:
    data = load_list()
    by_id = vendor_index(data)
    added = 0
    for raw in vendors:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        trade = str(raw.get("trade") or "").strip()
        area = str(raw.get("area") or "").strip()
        vid = str(raw.get("id") or "").strip() or slug_id(name, trade, area)
        if vid in by_id:
            continue
        row = {
            "id": vid,
            "name": name,
            "trade": trade,
            "area": area,
            "prefecture": raw.get("prefecture") or "",
            "city": raw.get("city") or "",
            "url": raw.get("url") or "",
            "contact_url": raw.get("contact_url") or "",
            "channel": raw.get("channel") or "phone",
            "contact_email": raw.get("contact_email") or "",
            "phone": raw.get("phone") or "",
            "status": raw.get("status") or "discovered",
            "source": raw.get("source") or "grok_discovery",
            "sole_proprietor_score": raw.get("sole_proprietor_score")
            or raw.get("sole_score")
            or "",
            "notes": raw.get("notes") or "",
            "discovered_at": raw.get("discovered_at") or now_iso()[:10],
            "contacted_at": "",
            "replied_at": "",
            "last_result": "",
            "alive_due_days": 90,
        }
        ensure_alive_fields(row, kind="repair")
        by_id[vid] = row
        added += 1
    data["vendors"] = list(by_id.values())
    if not dry_run:
        # ensure settings
        data.setdefault("settings", {})
        data["settings"].setdefault("daily_outreach_limit", data.get("daily_limit", 2))
        data["settings"].setdefault("alive_due_days", 90)
        save_list(data)
    return {"ok": True, "added": added, "total": len(data["vendors"]), "dry_run": dry_run}


def ensure_local_yaml() -> None:
    """example から正本を初回コピー（無ければ）。"""
    if LIST_PATH.is_file():
        return
    if EXAMPLE_PATH.is_file():
        data = load_list()
        save_list(data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--bootstrap", action="store_true", help="example → 正本 YAML 初回作成")
    ap.add_argument("--next", type=int, default=0)
    ap.add_argument("--trade", default="", help="職種フィルタ（--next）")
    ap.add_argument(
        "--alive-ok-first",
        action="store_true",
        default=True,
        help="alive_ok を先頭（既定）",
    )
    ap.add_argument("--no-alive-ok-first", action="store_true")
    ap.add_argument("--mark", metavar="ID")
    ap.add_argument("--status", default="contacted")
    ap.add_argument("--note", default="")
    ap.add_argument("--result", default="")
    ap.add_argument("--mark-alive", metavar="ID")
    ap.add_argument("--alive-status", default="ok")
    ap.add_argument("--alive-method", default="phone")
    ap.add_argument("--alive-queue", action="store_true")
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--merge-append", metavar="PATH")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.bootstrap:
        ensure_local_yaml()
        print(json.dumps({"ok": True, "path": str(LIST_PATH), "exists": LIST_PATH.is_file()}, ensure_ascii=False))
        return 0

    if args.alive_queue:
        data = load_list()
        vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
        items = build_alive_queue(vendors, kind="repair", limit=max(1, args.limit))
        print(
            json.dumps(
                {
                    "ok": True,
                    "kind": "repair",
                    "due_days_default": 90,
                    "count": len(items),
                    "vendors": [
                        {
                            "id": v.get("id"),
                            "name": v.get("name"),
                            "trade": v.get("trade"),
                            "phone": v.get("phone"),
                            "alive_status": v.get("alive_status"),
                            "alive_effective": effective_alive_status(v, kind="repair"),
                        }
                        for v in items
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.mark_alive:
        out = mark_vendor_alive(
            args.mark_alive,
            alive_status=args.alive_status,
            method=args.alive_method,
            note=args.note,
            dry_run=args.dry_run,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("ok") else 1

    if args.merge_append:
        raw = yaml.safe_load(Path(args.merge_append).read_text(encoding="utf-8")) or {}
        vendors = raw.get("vendors") if isinstance(raw, dict) else raw
        if not isinstance(vendors, list):
            print(json.dumps({"ok": False, "error": "no vendors"}, ensure_ascii=False))
            return 1
        out = merge_append(vendors, dry_run=args.dry_run)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.mark:
        out = mark_vendor(
            args.mark,
            status=args.status,
            note=args.note,
            result=args.result,
            dry_run=args.dry_run,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("ok") else 1

    if args.next > 0:
        alive_first = not args.no_alive_ok_first
        items = next_for_contact(
            limit=args.next,
            trade=args.trade,
            alive_ok_first=alive_first,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "count": len(items),
                    "alive_ok_first": alive_first,
                    "vendors": [
                        {
                            **v,
                            "alive_ok": is_alive_ok(v, kind="repair"),
                            "alive_effective": effective_alive_status(v, kind="repair"),
                        }
                        for v in items
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    out = summary()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
