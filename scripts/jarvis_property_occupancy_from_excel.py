#!/usr/bin/env python3
"""
★家賃マップ.xlsx → property_units（＋任意で occupancy events）を push。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_property_occupancy_from_excel.py
  python scripts/jarvis_property_occupancy_from_excel.py --push
  python scripts/jarvis_property_occupancy_from_excel.py --force-all-occupied --push
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
OUT_PATH = REPO / ".jarvis_state" / "property_occupancy.json"
DEFAULT_XLSX = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/20_【空室対策】【修繕】【売却】"
    "/21_【空室対策】募集,ステージング,物件管理"
    "/★家賃マップ.xlsx"
).expanduser()

PROPERTY_META = {
    "grandole-ii": {"name": "Grandole志賀本通II", "short": "II"},
    "grandole-i": {"name": "Grandole志賀本通I", "short": "I"},
    "caramel": {"name": "キャラメル", "short": "C"},
}
EXTRA_YAML = REPO / "config" / "property_units_extra.yaml"

ROOM_RE = re.compile(r"^(\d{3})号室$")
OCCUPIED_MARKERS = ("入居中", "入居済", "入居済み")
OCCUPIED_PATTERN = re.compile(r"入居\s*\d|→[^\n]*入居|入居[^\n]*")


def classify_status(text: str) -> str:
    t = (text or "").replace("\r", "").strip()
    if not t:
        return "occupied"
    if any(m in t for m in OCCUPIED_MARKERS):
        return "occupied"
    if OCCUPIED_PATTERN.search(t):
        return "occupied"
    if "空室" in t:
        return "vacant"
    return "occupied"


def _cell_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y/%m/%d")
    return str(v).strip()


def _as_rent(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        s = v.replace(",", "").strip()
        if re.fullmatch(r"\d+(\.\d+)?", s):
            return float(s)
    return None


def parse_rent_map(path: Path) -> list[dict[str, Any]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(max_col=12, values_only=True)]
    wb.close()

    def detect_property(row: list[Any]) -> tuple[str, str] | None:
        b1 = _cell_str(row[1] if len(row) > 1 else None)
        if not b1:
            return None
        if "志賀本通II" in b1 or b1.endswith("II"):
            if "Grandole" in b1 or "志賀本通" in b1:
                return "grandole-ii", PROPERTY_META["grandole-ii"]["name"]
        if "志賀本通I" in b1 and "II" not in b1:
            return "grandole-i", PROPERTY_META["grandole-i"]["name"]
        return None

    units: list[dict[str, Any]] = []
    current: tuple[str, str] | None = None

    for j, row in enumerate(rows):
        hit = detect_property(row)
        if hit:
            current = hit
            continue
        if not current:
            continue

        rooms: list[tuple[int, str]] = []
        for col, val in enumerate(row):
            s = _cell_str(val)
            m = ROOM_RE.match(s)
            if m:
                rooms.append((col, m.group(1)))
        if len(rooms) < 2:
            continue

        prop_id, prop_name = current
        status_row = rows[j + 1] if j + 1 < len(rows) else []
        for col, room in rooms:
            status_text = _cell_str(status_row[col] if col < len(status_row) else None)
            note_parts = [status_text] if status_text else []
            rent: float | None = None
            for k in range(j + 2, min(j + 8, len(rows))):
                # stop if next room header or property title
                peek = rows[k]
                if detect_property(peek):
                    break
                peek_rooms = sum(
                    1 for v in peek if ROOM_RE.match(_cell_str(v))
                )
                if peek_rooms >= 2:
                    break
                cell = peek[col] if col < len(peek) else None
                r = _as_rent(cell)
                if r is not None:
                    rent = r
                else:
                    cs = _cell_str(cell)
                    if (
                        cs
                        and "管理" not in cs
                        and "号室" not in cs
                        and cs not in note_parts
                        and len(cs) < 80
                    ):
                        note_parts.append(cs)
            status = classify_status(status_text)
            units.append(
                {
                    "id": f"{prop_id}-{room}",
                    "property_id": prop_id,
                    "property_name": prop_name,
                    "room": room,
                    "status": status,
                    "rent": rent,
                    "note": " / ".join(p for p in note_parts if p)[:500] or None,
                    "source": "excel",
                    "payload": {
                        "status_raw": status_text,
                        "short": PROPERTY_META[prop_id]["short"],
                    },
                }
            )

    by_id: dict[str, dict[str, Any]] = {}
    for u in units:
        by_id[u["id"]] = u
    return list(by_id.values())


def load_extra_units() -> list[dict[str, Any]]:
    if not EXTRA_YAML.is_file():
        return []
    try:
        import yaml  # type: ignore
    except ImportError:
        return []
    data = yaml.safe_load(EXTRA_YAML.read_text(encoding="utf-8")) or {}
    out: list[dict[str, Any]] = []
    for u in data.get("units") or []:
        pid = str(u.get("property_id") or "")
        room = str(u.get("room") or "")
        if not pid or not room:
            continue
        name = str(u.get("property_name") or PROPERTY_META.get(pid, {}).get("name") or pid)
        short = str(u.get("short") or PROPERTY_META.get(pid, {}).get("short") or pid)
        out.append(
            {
                "id": f"{pid}-{room}",
                "property_id": pid,
                "property_name": name,
                "room": room,
                "status": str(u.get("status") or "occupied"),
                "rent": float(u["rent"]) if u.get("rent") is not None else None,
                "note": u.get("note"),
                "source": "config",
                "payload": {"short": short, "status_raw": u.get("note") or ""},
            }
        )
    return out


def summarize(units: list[dict[str, Any]]) -> dict[str, Any]:
    by_prop: dict[str, dict[str, Any]] = {}
    vacant_labels: list[str] = []
    for u in units:
        pid = u["property_id"]
        bucket = by_prop.setdefault(
            pid,
            {
                "property_id": pid,
                "property_name": u["property_name"],
                "total": 0,
                "occupied": 0,
                "vacant": 0,
                "vacant_rooms": [],
            },
        )
        bucket["total"] += 1
        if u["status"] == "vacant":
            bucket["vacant"] += 1
            short = (u.get("payload") or {}).get("short") or pid
            label = f"{short}-{u['room']}"
            bucket["vacant_rooms"].append(u["room"])
            vacant_labels.append(label)
        else:
            bucket["occupied"] += 1

    total = len(units)
    occupied = sum(1 for u in units if u["status"] == "occupied")
    rate = round(100.0 * occupied / total, 1) if total else 0.0
    props = []
    for pid, b in by_prop.items():
        t = b["total"] or 1
        props.append(
            {
                **b,
                "rate_pct": round(100.0 * b["occupied"] / t, 1),
            }
        )
    return {
        "total": total,
        "occupied": occupied,
        "vacant": total - occupied,
        "rate_pct": rate,
        "vacant_labels": vacant_labels,
        "by_property": props,
    }


def force_all_occupied(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for u in units:
        nu = dict(u)
        if nu["status"] != "occupied":
            nu["status"] = "occupied"
            nu["payload"] = {
                **(nu.get("payload") or {}),
                "forced_occupied": True,
                "status_before_force": u["status"],
            }
        out.append(nu)
    return out


def sb_client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    return create_client(url, key)


def push_units(
    units: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    write_bootstrap_events: bool,
) -> None:
    sb = sb_client()
    now = datetime.now(tz=JST).isoformat()
    rows = []
    for u in units:
        rows.append(
            {
                "id": u["id"],
                "property_id": u["property_id"],
                "property_name": u["property_name"],
                "room": u["room"],
                "status": u["status"],
                "rent": u["rent"],
                "note": u.get("note"),
                "source": u.get("source") or "excel",
                "payload": u.get("payload") or {},
                "updated_at": now,
            }
        )
    # upsert in chunks
    for i in range(0, len(rows), 50):
        sb.table("property_units").upsert(rows[i : i + 50]).execute()

    if write_bootstrap_events:
        today = date.today().isoformat()
        events = []
        for u in units:
            events.append(
                {
                    "occurred_on": today,
                    "event_type": u["status"],
                    "property_id": u["property_id"],
                    "property_name": u["property_name"],
                    "room": u["room"],
                    "source": "excel",
                    "ref": "★家賃マップ.xlsx",
                    "note": "bootstrap from excel",
                    "payload": {"bootstrap": True},
                }
            )
        for i in range(0, len(events), 50):
            sb.table("property_occupancy_events").insert(events[i : i + 50]).execute()

    sb.table("sync_meta").upsert(
        {
            "key": "occupancy_summary",
            "value": json.dumps(summary, ensure_ascii=False),
            "updated_at": now,
        }
    ).execute()
    sb.table("sync_meta").upsert(
        {
            "key": "occupancy_excel_pushed_at",
            "value": now,
            "updated_at": now,
        }
    ).execute()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    ap.add_argument("--push", action="store_true")
    ap.add_argument(
        "--force-all-occupied",
        action="store_true",
        help="ユーザー確認どおり現状満室として全室 occupied にする",
    )
    ap.add_argument(
        "--bootstrap-history",
        action="store_true",
        help="初回のみ各号室の現況を events に1件ずつ書く",
    )
    args = ap.parse_args(argv)

    path = args.xlsx.expanduser()
    if not path.is_file():
        raise SystemExit(f"xlsx missing: {path}")

    units = parse_rent_map(path)
    # Excel に無い補完（キャラメル等）
    by_id = {u["id"]: u for u in units}
    for eu in load_extra_units():
        by_id[eu["id"]] = eu
    units = list(by_id.values())
    if args.force_all_occupied:
        units = force_all_occupied(units)
    summary = summarize(units)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {"updated": datetime.now(tz=JST).isoformat(), "summary": summary, "units": units},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"# wrote {OUT_PATH} units={len(units)} rate={summary['rate_pct']}%")

    if args.push:
        push_units(units, summary, write_bootstrap_events=args.bootstrap_history)
        print("# pushed property_units + occupancy_summary")

    print(json.dumps({"summary": summary, "unit_count": len(units)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
