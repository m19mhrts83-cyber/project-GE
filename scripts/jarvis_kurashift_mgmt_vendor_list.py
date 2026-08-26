#!/usr/bin/env python3
"""S9 管理会社開拓リスト — Excel 取込・状態・生存確認。

正本 YAML: config/kurashift_mgmt_vendor_list.yaml（.gitignore）
Excel 正本（空室一括送信）は壊さない。ここは KURASHIFT 投影用の副本。

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_list.py --summary
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_list.py \\
    --import-xlsx ".../★管理会社一覧.xlsx" --merge
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_list.py --next 2
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_list.py \\
    --mark ID --status contacted --note "Web送信"
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_list.py \\
    --mark-alive ID --alive-status ok --alive-method phone
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_list.py --alive-queue --limit 2
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
    ALIVE_STATUSES,
    build_alive_queue,
    effective_alive_status,
    ensure_alive_fields,
    is_alive_ok,
    mark_alive as mark_alive_fields,
)

LIST_PATH = REPO / "config" / "kurashift_mgmt_vendor_list.yaml"
EXAMPLE_PATH = REPO / "config" / "kurashift_mgmt_vendor_list.example.yaml"

DEFAULT_XLSX = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/20_【空室対策】【修繕】【売却】/"
    "21_【空室対策】募集,ステージング,物件管理/★管理会社一覧.xlsx"
)

STATUSES = frozenset(
    {"pending", "contacted", "replied", "skip", "discovered", "invalid"}
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug_id(name: str, area: str = "") -> str:
    base = f"mgmt-{name}-{area}".strip().lower()
    base = re.sub(r"\s+", "-", base)
    base = re.sub(r"[^a-z0-9\-ぁ-んァ-ヶ一-龥]", "", base)
    if len(base) >= 8:
        return base[:48]
    h = hashlib.sha256(base.encode()).hexdigest()[:8]
    return f"mgmt-{h}"


def load_list(path: Path | None = None) -> dict[str, Any]:
    p = path or LIST_PATH
    if not p.is_file():
        if EXAMPLE_PATH.is_file():
            data = yaml.safe_load(EXAMPLE_PATH.read_text(encoding="utf-8")) or {}
            data.setdefault("settings", {})
            data.setdefault("vendors", [])
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


def _cell(row: tuple[Any, ...], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    val = row[idx]
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    return str(val).strip().replace("\n", " ")


def _mark_true(val: str) -> bool:
    s = (val or "").strip()
    return s in ("〇", "○", "有り", "あり", "有", "OK", "ok", "1", "True", "true")


def _status_hint_from_notes(notes: str) -> str:
    n = notes or ""
    if "戸別管理不可" in n or "戸建て管理不可" in n:
        return "skip"
    if "問い合わせ中→OK" in n or "戸別管理問い合わせ中→OK" in n or "管理OK" in n:
        return "replied"
    if "問い合わせ中" in n:
        return "contacted"
    return "pending"


def import_mgmt_xlsx(
    path: Path,
    *,
    dry_run: bool,
    merge: bool = True,
) -> dict[str, Any]:
    try:
        import openpyxl
    except ImportError as exc:
        raise SystemExit("openpyxl required for --import-xlsx") from exc

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet_name = "一覧" if "一覧" in wb.sheetnames else wb.sheetnames[0]
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    # header row: find row with 会社名
    header_i = 0
    for i, r in enumerate(rows[:10]):
        cells = [str(c or "") for c in (r or ())]
        if any("会社名" in c for c in cells):
            header_i = i
            break
    header = rows[header_i] if rows else ()
    col = {str(h or "").replace("\n", ""): i for i, h in enumerate(header)}

    def idx(*names: str) -> int:
        for n in names:
            if n in col:
                return col[n]
            for k, i in col.items():
                if n in k:
                    return i
        return -1

    i_no = idx("No.")
    i_pref = idx("県")
    i_city = idx("市")
    i_sta = idx("駅")
    i_name = idx("会社名")
    i_area = idx("物件エリア")
    i_url = idx("URL")
    i_notes = idx("備考")
    i_buy = idx("購入")
    i_lease = idx("賃貸仲介")
    i_mgmt = idx("賃貸管理")
    i_repair = idx("修繕")
    i_sale = idx("売却査定")
    i_kodate_ok = idx("戸建管理OK")
    i_form = idx("問い合わせフォーム")
    i_mail = idx("mail", "個別メール")
    i_tel = idx("tel")
    i_result = idx("問い合わせ結果")

    existing = load_list() if merge else {"settings": {}, "vendors": []}
    by_id = vendor_index(existing)
    by_name = {
        str(v.get("name") or "").strip(): v
        for v in (existing.get("vendors") or [])
        if isinstance(v, dict) and v.get("name")
    }
    added = 0
    updated = 0
    skipped = 0

    for r in rows[header_i + 1 :]:
        if not r:
            continue
        name = _cell(r, i_name)
        if not name or name in ("記入例", "会社名", "〇〇"):
            continue
        # skip title-ish / placeholder
        if name == "管理会社一覧" or "〇〇" in name:
            continue
        url = _cell(r, i_url)
        if "〇〇" in url or url in ("〇〇",):
            continue
        pref = _cell(r, i_pref)
        city = _cell(r, i_city)
        station = _cell(r, i_sta)
        prop_area = _cell(r, i_area)
        area = " ".join(x for x in (pref, city, station) if x).strip()
        url = _cell(r, i_url)
        if url and not url.startswith("http"):
            url = f"https://{url}"
        notes = _cell(r, i_notes)
        result = _cell(r, i_result)
        services = {
            "buy": _mark_true(_cell(r, i_buy)),
            "lease_broker": _mark_true(_cell(r, i_lease)),
            "lease_mgmt": _mark_true(_cell(r, i_mgmt)),
            "repair": _mark_true(_cell(r, i_repair)),
            "sale_appraisal": _mark_true(_cell(r, i_sale)),
            "kodate_mgmt_ok": _mark_true(_cell(r, i_kodate_ok)),
        }
        form = _cell(r, i_form)
        contact_url = url if form in ("有り", "あり", "〇", "○") else url
        email = _cell(r, i_mail)
        phone = _cell(r, i_tel)
        no = _cell(r, i_no)
        vid = slug_id(name, city or pref)
        if no.isdigit():
            vid = f"mgmt-{int(no):03d}-{slug_id(name, '')[5:20]}"

        status = _status_hint_from_notes(notes)
        if "不可" in notes:
            status = "skip"

        row: dict[str, Any] = {
            "id": vid,
            "name": name,
            "area": area or prop_area,
            "prefecture": f"{pref}県" if pref and not pref.endswith("県") else pref,
            "city": city,
            "station": station,
            "property_area": prop_area,
            "url": url,
            "contact_url": contact_url,
            "channel": "web_form" if url else "phone",
            "contact_email": email if "@" in email else "",
            "phone": phone,
            "status": status if status in STATUSES else "pending",
            "source": "mgmt_xlsx",
            "notes": notes,
            "last_result": result,
            "services": services,
            "discovered_at": now_iso()[:10],
            "contacted_at": "",
            "replied_at": "",
            "alive_checked_at": "",
            "alive_status": "unknown",
            "alive_method": "",
            "alive_note": "",
            "alive_due_days": 180,
        }
        if status == "contacted":
            row["contacted_at"] = now_iso()[:10]
        if status == "replied":
            row["replied_at"] = now_iso()[:10]
            row["contacted_at"] = row["contacted_at"] or now_iso()[:10]

        ensure_alive_fields(row, kind="mgmt")

        prev = by_id.get(vid) or by_name.get(name)
        if prev:
            # keep outreach/alive progress
            for k in (
                "status",
                "contacted_at",
                "replied_at",
                "alive_checked_at",
                "alive_status",
                "alive_method",
                "alive_note",
                "last_result",
            ):
                if prev.get(k) and k in (
                    "alive_checked_at",
                    "alive_status",
                    "alive_method",
                    "alive_note",
                    "contacted_at",
                    "replied_at",
                ):
                    row[k] = prev[k]
                elif k == "status" and prev.get("status") in (
                    "contacted",
                    "replied",
                    "skip",
                    "invalid",
                ):
                    # import hint より既存の開拓進捗を優先
                    row["status"] = prev["status"]
                elif k == "last_result" and prev.get("last_result"):
                    row["last_result"] = prev["last_result"]
            row["id"] = prev["id"]
            by_id[row["id"]] = row
            updated += 1
        else:
            by_id[vid] = row
            added += 1

    vendors = list(by_id.values())
    vendors.sort(key=lambda v: str(v.get("id") or ""))
    settings = existing.get("settings") or {}
    settings.setdefault("daily_outreach_limit", 2)
    settings.setdefault("alive_due_days", 180)
    settings.setdefault("source_xlsx", str(path))
    out_data = {"settings": settings, "vendors": vendors}
    result = {
        "ok": True,
        "sheet": sheet_name,
        "path": str(path),
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "total": len(vendors),
        "dry_run": dry_run,
    }
    if not dry_run:
        save_list(out_data)
    return result


def summary() -> dict[str, Any]:
    data = load_list()
    vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
    counts: dict[str, int] = {}
    alive_ok_n = 0
    for v in vendors:
        ensure_alive_fields(v, kind="mgmt")
        st = str(v.get("status") or "pending")
        counts[st] = counts.get(st, 0) + 1
        if is_alive_ok(v, kind="mgmt"):
            alive_ok_n += 1
    return {
        "ok": True,
        "total": len(vendors),
        "by_status": counts,
        "alive_ok": alive_ok_n,
        "yaml_exists": LIST_PATH.is_file(),
        "settings": data.get("settings") or {},
    }


def next_pending(*, limit: int) -> list[dict[str, Any]]:
    data = load_list()
    out: list[dict[str, Any]] = []
    for v in data.get("vendors") or []:
        if not isinstance(v, dict):
            continue
        if str(v.get("status") or "pending") not in ("pending", "discovered"):
            continue
        ensure_alive_fields(v, kind="mgmt")
        out.append(v)
        if len(out) >= limit:
            break
    return out


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
    ensure_alive_fields(v, kind="mgmt")
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
    mark_alive_fields(v, status=st, method=method, note=note, kind="mgmt")
    if not dry_run:
        save_list(data)
    return {
        "ok": True,
        "vendor": v,
        "alive_effective": effective_alive_status(v, kind="mgmt"),
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
        vid = str(raw.get("id") or "").strip() or slug_id(
            name, str(raw.get("area") or "")
        )
        if vid in by_id:
            continue
        row = {
            "id": vid,
            "name": name,
            "area": raw.get("area") or "",
            "prefecture": raw.get("prefecture") or "",
            "city": raw.get("city") or "",
            "station": raw.get("station") or "",
            "property_area": raw.get("property_area") or "",
            "url": raw.get("url") or "",
            "contact_url": raw.get("contact_url") or raw.get("url") or "",
            "channel": raw.get("channel") or "web_form",
            "contact_email": raw.get("contact_email") or "",
            "phone": raw.get("phone") or "",
            "status": raw.get("status") or "discovered",
            "source": raw.get("source") or "grok_discovery",
            "notes": raw.get("notes") or "",
            "services": raw.get("services") or {},
            "discovered_at": raw.get("discovered_at") or now_iso()[:10],
            "contacted_at": "",
            "replied_at": "",
            "last_result": "",
            "alive_due_days": 180,
        }
        ensure_alive_fields(row, kind="mgmt")
        by_id[vid] = row
        added += 1
    data["vendors"] = list(by_id.values())
    if not dry_run:
        save_list(data)
    return {"ok": True, "added": added, "total": len(data["vendors"]), "dry_run": dry_run}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--import-xlsx", metavar="PATH", nargs="?", const=str(DEFAULT_XLSX))
    ap.add_argument("--merge", action="store_true", default=True)
    ap.add_argument("--no-merge", action="store_true")
    ap.add_argument("--next", type=int, default=0)
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
    merge = not args.no_merge

    if args.alive_queue:
        data = load_list()
        vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
        items = build_alive_queue(vendors, kind="mgmt", limit=max(1, args.limit))
        print(
            json.dumps(
                {
                    "ok": True,
                    "kind": "mgmt",
                    "count": len(items),
                    "vendors": [
                        {
                            "id": v.get("id"),
                            "name": v.get("name"),
                            "phone": v.get("phone"),
                            "url": v.get("url"),
                            "alive_status": v.get("alive_status"),
                            "alive_effective": effective_alive_status(v, kind="mgmt"),
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

    if args.import_xlsx:
        out = import_mgmt_xlsx(
            Path(args.import_xlsx), dry_run=args.dry_run, merge=merge
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"MGMT_VENDOR_LIST_RESULT:{json.dumps(out, ensure_ascii=False)}")
        return 0

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
        items = next_pending(limit=args.next)
        print(
            json.dumps(
                {"ok": True, "count": len(items), "vendors": items},
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
