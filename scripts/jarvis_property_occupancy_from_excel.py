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
YEAR1_TOTAL_RE = re.compile(
    r"1年目[^\d]{0,16}合計\s*([\d,]+)\s*円|"
    r"1年目[^\d]{0,8}([\d,]+)\s*円"
)
DISCOUNT_RE = re.compile(
    r"(?:家賃)?\s*[▲△]\s*([\d,]+)\s*円|"
    r"割引\s*([\d,]+)\s*円|"
    r"-\s*([\d,]+)\s*円"
)
CAMPAIGN_UNTIL_RE = re.compile(
    r"(?:〜|～)\s*(\d{1,2})\s*月\s*まで|"
    r"(?:〜|～)?\s*(\d{1,2}/\d{1,2})\s*まで|"
    r"(\d{2}/\d{1,2})\s*まで"
)


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


def _extract_campaign_fields(memos: list[str]) -> dict[str, Any]:
    """メモ行から 1年目・割引・キャンペーン期限を推定。"""
    joined = "\n".join(memos)
    out: dict[str, Any] = {}
    year1_amounts: list[float] = []
    for m in YEAR1_TOTAL_RE.finditer(joined):
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        try:
            year1_amounts.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    if year1_amounts:
        # 大きい方を合計候補、小さい方を家賃候補（両方あるとき）
        amounts = sorted(set(year1_amounts))
        if len(amounts) >= 2:
            out["rent_year1"] = amounts[0]
            out["total_year1"] = amounts[-1]
        else:
            v = amounts[0]
            if v >= 48000:
                out["total_year1"] = v
            else:
                out["rent_year1"] = v

    for m in DISCOUNT_RE.finditer(joined):
        raw = next((g for g in m.groups() if g), None)
        if not raw:
            continue
        try:
            out["discount_yen"] = float(raw.replace(",", ""))
            break
        except ValueError:
            continue

    for m in CAMPAIGN_UNTIL_RE.finditer(joined):
        raw = next((g for g in m.groups() if g), None)
        if raw:
            out["campaign_until"] = raw
            break

    plan_bits = [t for t in memos if "1年目" in t or "▲" in t or "△" in t]
    if plan_bits:
        out["plan_note"] = " / ".join(plan_bits)[:240]
    return out


def parse_rent_map(path: Path) -> list[dict[str, Any]]:
    """★家賃マップ.xlsx を号室単位で読む。

    Excel は号室列ごとに「状態」「（合計）」「家賃」「管理費」＋メモ行が並ぶ。
    rent=現状家賃、payload に management_fee / total_rent と
    rent_year1 / rent_year2 / total_year* / discount_* / memo_log を載せる。
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(max_col=14, values_only=True)]
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

    def row_label(row: list[Any]) -> str:
        """B列（index 1）の行ラベルのみ使う（J列は右側の合計欄用）。"""
        s = _cell_str(row[1] if len(row) > 1 else None)
        if s in ("家賃", "管理費", "合計"):
            return s
        return ""

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

        # 号室ブロック終端（次の号室ヘッダ or 物件タイトル or 空行が続く）
        end = min(j + 12, len(rows))
        for k in range(j + 2, end):
            peek = rows[k]
            if detect_property(peek):
                end = k
                break
            peek_rooms = sum(1 for v in peek if ROOM_RE.match(_cell_str(v)))
            if peek_rooms >= 2:
                end = k
                break
            # 別表（G2 / 日付 など）に入ったら止める
            b2 = _cell_str(peek[2] if len(peek) > 2 else None)
            if re.fullmatch(r"G\d+", b2) or isinstance(
                peek[3] if len(peek) > 3 else None, datetime
            ):
                end = k
                break
            # 部屋列がすべて空ならメモ収集を打ち切り（ただし家賃/管理費ラベル行は残す）
            room_vals = [peek[c] if c < len(peek) else None for c, _ in rooms]
            if all(v is None or _cell_str(v) == "" for v in room_vals) and row_label(
                peek
            ) == "":
                nxt = rows[k + 1] if k + 1 < len(rows) else []
                if row_label(nxt) not in ("家賃", "管理費", "合計"):
                    end = k
                    break

        rent_by_col: dict[int, float] = {}
        mgmt_by_col: dict[int, float] = {}
        total_by_col: dict[int, float] = {}
        unlabeled_totals: dict[int, list[float]] = {col: [] for col, _ in rooms}
        memo_by_col: dict[int, list[str]] = {col: [] for col, _ in rooms}

        for k in range(j + 2, end):
            peek = rows[k]
            label = row_label(peek)
            for col, _room in rooms:
                cell = peek[col] if col < len(peek) else None
                r = _as_rent(cell)
                cs = _cell_str(cell)
                if label == "家賃" and r is not None:
                    rent_by_col[col] = r
                elif label == "管理費" and r is not None:
                    mgmt_by_col[col] = r
                elif label == "合計" and r is not None:
                    total_by_col[col] = r
                elif r is not None and label == "":
                    if r <= 8000 and col not in mgmt_by_col:
                        mgmt_by_col[col] = r
                    else:
                        unlabeled_totals[col].append(r)
                        if col not in total_by_col:
                            total_by_col[col] = r
                elif (
                    cs
                    and "号室" not in cs
                    and len(cs) < 120
                    and not re.fullmatch(r"G\d+", cs)
                    and (label == "" or r is None)
                ):
                    # 家賃／管理費行でも文言（1年目メモ等）なら控える
                    memo_by_col[col].append(cs)

            # 号室列の右隣（メモがはみ出すケース）を末尾号室へ寄せる
            if rooms:
                last_col, _ = rooms[-1]
                side = peek[last_col + 1] if last_col + 1 < len(peek) else None
                side_s = _cell_str(side)
                if (
                    side_s
                    and _as_rent(side) is None
                    and "号室" not in side_s
                    and ("1年目" in side_s or "▲" in side_s or "△" in side_s)
                    and side_s not in memo_by_col[last_col]
                ):
                    memo_by_col[last_col].append(side_s)

        for col, room in rooms:
            status_text = _cell_str(
                status_row[col] if col < len(status_row) else None
            )
            rent_labeled = rent_by_col.get(col)
            mgmt = mgmt_by_col.get(col)
            labeled_total = total_by_col.get(col)
            # 賃料合計は家賃+管理費を正とする（Excelの先頭合計行は割引前のことがある）
            if rent_labeled is not None:
                rent = float(rent_labeled)
                total = float(rent) + (float(mgmt) if mgmt is not None else 0.0)
            elif labeled_total is not None and mgmt is not None:
                total = float(labeled_total)
                rent = total - float(mgmt)
            elif labeled_total is not None:
                total = float(labeled_total)
                rent = total
            else:
                total = None
                rent = None

            memos = list(memo_by_col.get(col) or [])
            note_parts = [status_text] if status_text else []
            for mtxt in memos:
                if mtxt and mtxt not in note_parts:
                    note_parts.append(mtxt)
            status = classify_status(status_text)
            campaign = _extract_campaign_fields(memos)

            rent_year2 = float(rent_labeled) if rent_labeled is not None else (
                float(rent) if rent is not None else None
            )
            total_year2 = None
            if rent_year2 is not None:
                total_year2 = float(rent_year2) + (
                    float(mgmt) if mgmt is not None else 0.0
                )
            elif total is not None:
                total_year2 = float(total)

            rent_year1 = campaign.get("rent_year1")
            total_year1 = campaign.get("total_year1")
            discount_yen = campaign.get("discount_yen")

            if total_year1 is None and rent_year1 is not None:
                total_year1 = float(rent_year1) + (
                    float(mgmt) if mgmt is not None else 0.0
                )
            if rent_year1 is None and total_year1 is not None and mgmt is not None:
                rent_year1 = float(total_year1) - float(mgmt)
            if (
                discount_yen is None
                and total_year2 is not None
                and total_year1 is not None
            ):
                discount_yen = float(total_year2) - float(total_year1)
            if (
                total_year1 is None
                and discount_yen is not None
                and total_year2 is not None
            ):
                total_year1 = float(total_year2) - float(discount_yen)
                if rent_year1 is None and mgmt is not None:
                    rent_year1 = float(total_year1) - float(mgmt)
            if (
                rent_year1 is None
                and discount_yen is not None
                and rent_year2 is not None
            ):
                rent_year1 = float(rent_year2) - float(discount_yen)

            discount_rate = None
            if (
                discount_yen is not None
                and total_year2 is not None
                and float(total_year2) > 0
            ):
                discount_rate = round(
                    100.0 * float(discount_yen) / float(total_year2), 1
                )

            now_iso = datetime.now(tz=JST).isoformat()
            memo_log: list[dict[str, str]] = []
            for mtxt in note_parts:
                if not mtxt:
                    continue
                memo_log.append(
                    {"at": now_iso, "text": mtxt[:400], "source": "excel"}
                )

            payload: dict[str, Any] = {
                "status_raw": status_text,
                "short": PROPERTY_META[prop_id]["short"],
                "memo_log": memo_log,
            }
            if mgmt is not None:
                payload["management_fee"] = mgmt
                payload["mgmt_fee"] = mgmt
            if total is not None:
                payload["total_rent"] = total
            if rent_year1 is not None:
                payload["rent_year1"] = rent_year1
            if rent_year2 is not None:
                payload["rent_year2"] = rent_year2
            if total_year1 is not None:
                payload["total_year1"] = total_year1
            if total_year2 is not None:
                payload["total_year2"] = total_year2
            if discount_yen is not None and float(discount_yen) > 0:
                payload["discount_yen"] = discount_yen
            if discount_rate is not None and float(discount_rate) > 0:
                payload["discount_rate"] = discount_rate
            if campaign.get("plan_note"):
                payload["plan_note"] = campaign["plan_note"]
            if campaign.get("campaign_until"):
                payload["campaign_until"] = campaign["campaign_until"]
            if unlabeled_totals.get(col):
                payload["listing_totals_raw"] = unlabeled_totals[col]

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
                    "payload": payload,
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
        rent = float(u["rent"]) if u.get("rent") is not None else None
        mgmt = float(u["management_fee"]) if u.get("management_fee") is not None else None
        total = float(u["total_rent"]) if u.get("total_rent") is not None else None
        if total is None and rent is not None:
            total = rent + (mgmt or 0.0)
        payload: dict[str, Any] = {"short": short, "status_raw": u.get("note") or ""}
        if mgmt is not None:
            payload["management_fee"] = mgmt
        if total is not None:
            payload["total_rent"] = total
        out.append(
            {
                "id": f"{pid}-{room}",
                "property_id": pid,
                "property_name": name,
                "room": room,
                "status": str(u.get("status") or "occupied"),
                "rent": rent,
                "note": u.get("note"),
                "source": "config",
                "payload": payload,
                "fill_missing": bool(u.get("fill_missing")),
            }
        )
    return out


def merge_extra_units(
    excel_units: list[dict[str, Any]],
    extra_units: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Excel 結果に config 補完をマージ。

    - 新規 ID: そのまま追加
    - 既存 ID + fill_missing: Excel の rent が空のときだけ家賃・管理費を埋める
    - 既存 ID（fill_missing なし）: 従来どおり config で置換（キャラメル等）
    """
    by_id = {u["id"]: u for u in excel_units}
    for eu in extra_units:
        eid = eu["id"]
        existing = by_id.get(eid)
        if existing is None:
            nu = {k: v for k, v in eu.items() if k != "fill_missing"}
            by_id[eid] = nu
            continue
        if eu.get("fill_missing"):
            if existing.get("rent") is not None:
                continue
            existing["rent"] = eu.get("rent")
            payload = dict(existing.get("payload") or {})
            ep = eu.get("payload") or {}
            if ep.get("management_fee") is not None:
                payload["management_fee"] = ep["management_fee"]
                payload["mgmt_fee"] = ep["management_fee"]
            if ep.get("total_rent") is not None:
                payload["total_rent"] = ep["total_rent"]
            # 計画（2年目）が空なら補完家賃を計画としても載せる
            if payload.get("rent_year2") is None and eu.get("rent") is not None:
                payload["rent_year2"] = eu["rent"]
            if payload.get("total_year2") is None and ep.get("total_rent") is not None:
                payload["total_year2"] = ep["total_rent"]
            existing["payload"] = payload
            note_add = eu.get("note")
            if note_add:
                base = (existing.get("note") or "").strip()
                if note_add not in base:
                    existing["note"] = f"{base} / {note_add}".strip(" /")
            existing["source"] = f"{existing.get('source') or 'excel'}+config"
            continue
        by_id[eid] = {k: v for k, v in eu.items() if k != "fill_missing"}
    # 最終: rent があるのに year2 が空ならフォールバック
    for u in by_id.values():
        payload = dict(u.get("payload") or {})
        rent = u.get("rent")
        mgmt = payload.get("management_fee")
        total = payload.get("total_rent")
        if payload.get("rent_year2") is None and rent is not None:
            payload["rent_year2"] = rent
        if payload.get("total_year2") is None:
            if total is not None:
                payload["total_year2"] = total
            elif rent is not None:
                payload["total_year2"] = float(rent) + (
                    float(mgmt) if mgmt is not None else 0.0
                )
        u["payload"] = payload
    return list(by_id.values())


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
                "rent_sum": 0.0,
                "mgmt_sum": 0.0,
                "total_rent_sum": 0.0,
            },
        )
        bucket["total"] += 1
        rent = u.get("rent")
        mgmt = (u.get("payload") or {}).get("management_fee")
        total_rent = (u.get("payload") or {}).get("total_rent")
        if total_rent is None and rent is not None:
            total_rent = float(rent) + (float(mgmt) if mgmt is not None else 0.0)
        if rent is not None:
            bucket["rent_sum"] += float(rent)
        if mgmt is not None:
            bucket["mgmt_sum"] += float(mgmt)
        if total_rent is not None:
            bucket["total_rent_sum"] += float(total_rent)
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


def _merge_memo_log(
    existing: list[Any] | None,
    incoming: list[Any] | None,
) -> list[dict[str, str]]:
    """ui/jarvis/mail を残し、excel 由来は本文重複を避けて追記。"""
    out: list[dict[str, str]] = []
    seen_excel: set[str] = set()
    for item in existing or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        source = str(item.get("source") or "excel")
        at = str(item.get("at") or "")
        entry = {"at": at, "text": text[:400], "source": source}
        out.append(entry)
        if source == "excel":
            seen_excel.add(text)
    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        source = str(item.get("source") or "excel")
        if source == "excel" and text in seen_excel:
            continue
        if source == "excel":
            seen_excel.add(text)
        out.append(
            {
                "at": str(item.get("at") or datetime.now(tz=JST).isoformat()),
                "text": text[:400],
                "source": source,
            }
        )
    return out[-80:]


def push_units(
    units: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    write_bootstrap_events: bool,
) -> None:
    sb = sb_client()
    now = datetime.now(tz=JST).isoformat()
    existing_by_id: dict[str, dict[str, Any]] = {}
    try:
        res = sb.table("property_units").select("id,payload,note").execute()
        for row in res.data or []:
            existing_by_id[str(row["id"])] = row
    except Exception as e:  # noqa: BLE001
        print(f"# warn: could not load existing units for memo merge: {e}", file=sys.stderr)

    rows = []
    for u in units:
        payload = dict(u.get("payload") or {})
        prev = existing_by_id.get(u["id"]) or {}
        prev_payload = prev.get("payload") if isinstance(prev.get("payload"), dict) else {}
        payload["memo_log"] = _merge_memo_log(
            (prev_payload or {}).get("memo_log"),
            payload.get("memo_log"),
        )
        # note は Excel 側を正（最新要約）。空なら既存を残す
        note = u.get("note") or prev.get("note")
        rows.append(
            {
                "id": u["id"],
                "property_id": u["property_id"],
                "property_name": u["property_name"],
                "room": u["room"],
                "status": u["status"],
                "rent": u["rent"],
                "note": note,
                "source": u.get("source") or "excel",
                "payload": payload,
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
    # Excel に無い補完（キャラメル等）／家賃空欄の fill_missing
    units = merge_extra_units(units, load_extra_units())
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
