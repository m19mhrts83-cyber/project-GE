#!/usr/bin/env python3
"""家賃入金明細の取り込み（LEAF / ミニテック / Tcell PDF ＋ Zaim 口座入金合算）。

使い方:
  python scripts/jarvis_rent_deposit_ingest.py
  python scripts/jarvis_rent_deposit_ingest.py --ym 2026-07
  python scripts/jarvis_rent_deposit_ingest.py --status

出力: .jarvis_state/rent_deposits.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
OUT_PATH = STATE_DIR / "rent_deposits.json"
CONFIG_PATH = REPO / "config" / "rent_step_up.yaml"
ONEDRIVE_215 = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
).expanduser()
PARTNER = ONEDRIVE_215 / "C2_ルーティン作業" / "26_パートナー社への相談"
TAX = ONEDRIVE_215 / "50_税金,確定申告"
ZAIM_CSV = TAX / "2026年度" / "Zaim.2026年度.csv"

LEAF_NAME_RE = re.compile(r"LEAF_送金明細書_(\d{4})年(\d{1,2})月\.pdf$", re.I)
MINI_NAME_RE = re.compile(r"ミニテック_送金のご案内_(\d{4})年(\d{1,2})月\.pdf$")
TCELL_YM_RE = re.compile(r"(\d{4})年(\d{1,2})月分|(\d{1,2})月分")
ZEN = str.maketrans("０１２３４５６７８９．", "0123456789.")


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.is_file() and yaml is not None:
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return {}


def pdf_text(path: Path) -> str:
    if PdfReader is None:
        raise RuntimeError("pypdf が必要です")
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def yen_int(s: str) -> int | None:
    t = (s or "").replace(",", "").replace("¥", "").replace("円", "").strip()
    if not t:
        return None
    try:
        return int(float(t))
    except ValueError:
        return None


def match_property(text: str) -> str | None:
    t = text.replace("Ｇ", "G").replace("ｒ", "r").replace("ａ", "a").replace(
        "ｎ", "n"
    ).replace("ｄ", "d").replace("ｏ", "o").replace("ｌ", "l").replace("ｅ", "e")
    t = re.sub(r"\s+", "", t)
    if "キャラメル" in text or "キャラメル" in t:
        return "caramel"
    if re.search(r"志賀本通\s*[IⅠ1１]\b|志賀本通I(?!I)|Grandole志賀本通I(?!I)", text):
        return "grandole-i"
    if "志賀本通Ⅰ" in text or "志賀本通I" in text and "II" not in text and "Ⅱ" not in text:
        if "Ⅱ" in text or "II" in text:
            return "grandole-ii"
        return "grandole-i"
    if "志賀本通Ⅱ" in text or "志賀本通II" in text or "Grandole志賀本通II" in text:
        return "grandole-ii"
    if "Grandole" in text and ("I" in text or "Ⅰ" in text):
        if "II" in text or "Ⅱ" in text:
            return "grandole-ii"
        return "grandole-i"
    return None


def parse_leaf(path: Path, text: str) -> list[dict[str, Any]]:
    m = LEAF_NAME_RE.search(path.name)
    ym = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}" if m else None
    pid = match_property(text) or "grandole-i"
    out: list[dict[str, Any]] = []
    # 2026/07105山中　駿之介 45,000 4,000 49,000
    for m in re.finditer(
        r"(\d{4})/(\d{2})(\d{3})\D+([\d,]+)\s+([\d,]+)\s+([\d,]+)",
        text,
    ):
        row_ym = f"{m.group(1)}-{m.group(2)}"
        room = m.group(3)
        rent = yen_int(m.group(4))
        cam = yen_int(m.group(5))
        if rent is None:
            continue
        if "空" in m.group(0):
            continue
        out.append(
            {
                "source": "leaf_pdf",
                "ym": ym or row_ym,
                "property_id": pid,
                "room": room,
                "rent_yen": rent,
                "cam_yen": cam,
                "label": f"LEAF {pid}-{room}",
                "file": str(path),
            }
        )
    return out


def parse_minitech(path: Path, text: str) -> list[dict[str, Any]]:
    m = MINI_NAME_RE.search(path.name)
    pay_ym = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}" if m else None
    # 見出しからも
    hm = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*[　 ]*◇◇\s*送金", text)
    if hm:
        pay_ym = f"{int(hm.group(1)):04d}-{int(hm.group(2)):02d}"
    pid = match_property(text) or "grandole-i"
    # 未納ブロック以降はスキップ
    body = text.split("《　未納内訳　》")[0]
    out: list[dict[str, Any]] = []
    current_room: str | None = None
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        rm = re.match(r"^(\d{3})\s+", line)
        if rm:
            current_room = rm.group(1)
            if "空" in line or "家主様管理" in line:
                current_room = None
                continue
        if current_room is None:
            continue
        # ２６.０７ 家賃 45,000 / 26.07 家賃 45000
        line_n = line.translate(ZEN)
        mm = re.search(
            r"(?:(\d{2})\.(\d{2})|(\d{4})/(\d{2}))\s*家賃\s*([0-9,]+)",
            line_n,
        )
        if not mm:
            continue
        if mm.group(1):
            row_ym = f"20{int(mm.group(1)):02d}-{int(mm.group(2)):02d}"
        else:
            row_ym = f"{int(mm.group(3)):04d}-{int(mm.group(4)):02d}"
        # 支払月と一致する家賃行だけ（滞納遡及は別）
        if pay_ym and row_ym != pay_ym:
            continue
        rent = yen_int(mm.group(5))
        if rent is None:
            continue
        out.append(
            {
                "source": "minitech_pdf",
                "ym": pay_ym or row_ym,
                "property_id": pid,
                "room": current_room,
                "rent_yen": rent,
                "cam_yen": None,
                "label": f"ミニテック {pid}-{current_room}",
                "file": str(path),
            }
        )
    return out


def parse_tcell(path: Path, text: str) -> list[dict[str, Any]]:
    pid = match_property(text) or match_property(path.name)
    if pid is None:
        if "キャラメル" in path.name:
            pid = "caramel"
        elif "Grandole" in path.name or "志賀" in path.name:
            pid = "grandole-i"
    ym = None
    m = re.search(r"\((\d{4})年(\d{1,2})月分\)", text)
    if m:
        ym = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    else:
        m2 = TCELL_YM_RE.search(path.name)
        if m2:
            if m2.group(1):
                ym = f"{int(m2.group(1)):04d}-{int(m2.group(2)):02d}"
            elif m2.group(3):
                # 年なし → ファイルの親フォルダ日付から推定せず、スキップしにくく当年
                y = datetime.now(JST).year
                ym = f"{y:04d}-{int(m2.group(3)):02d}"

    out: list[dict[str, Any]] = []
    # 行: 101 5月28日 ¥71,400 2026年6月 ¥61,000 ¥3,000 ...
    for m in re.finditer(
        r"(?m)^(\d{3})\s+\S+\s+¥?([\d,]+)\s+(\d{4})年(\d{1,2})月\s+¥?([\d,]+)",
        text,
    ):
        room = m.group(1)
        row_ym = f"{int(m.group(3)):04d}-{int(m.group(4)):02d}"
        rent = yen_int(m.group(5))
        if rent is None:
            continue
        out.append(
            {
                "source": "tcell_pdf",
                "ym": ym or row_ym,
                "property_id": pid or "unknown",
                "room": room,
                "rent_yen": rent,
                "cam_yen": None,
                "label": f"Tcell {pid}-{room}",
                "file": str(path),
            }
        )
    # 単号室明細書で行が取れない場合: 物件名に号室 + 家賃 ¥
    if not out and pid:
        room_m = re.search(r"(?:物件名[:：].*?|Ⅰ|I)\s*(\d{3})\b|(\d{3})\s*　", path.name + text[:400])
        room = None
        if room_m:
            room = room_m.group(1) or room_m.group(2)
        if not room:
            rm2 = re.search(r"Grandole[^0-9]*(\d{3})", path.name)
            if rm2:
                room = rm2.group(1)
        rent_m = re.search(r"家賃\s*¥?([\d,]+)", text)
        rent = yen_int(rent_m.group(1)) if rent_m else None
        if room and rent is not None:
            out.append(
                {
                    "source": "tcell_pdf",
                    "ym": ym,
                    "property_id": pid,
                    "room": room,
                    "rent_yen": rent,
                    "cam_yen": None,
                    "label": f"Tcell {pid}-{room}",
                    "file": str(path),
                }
            )
    return out


def iter_leaf_pdfs() -> list[Path]:
    root = PARTNER / "104_LEAF" / "1.受信添付(Stock)"
    if not root.is_dir():
        return []
    return sorted(root.rglob("LEAF_送金明細書_*.pdf"))


def iter_minitech_pdfs() -> list[Path]:
    if not TAX.is_dir():
        return []
    return sorted(TAX.rglob("ミニテック_送金のご案内_*.pdf"))


def iter_tcell_pdfs() -> list[Path]:
    root = PARTNER / "103_Tcell" / "1.受信添付(Stock)"
    if not root.is_dir():
        return []
    files: list[Path] = []
    for p in root.rglob("*.pdf"):
        if "明細" in p.name or "精算" in p.name:
            files.append(p)
    return sorted(files)


def zaim_bank_inflows(ym: str | None = None) -> list[dict[str, Any]]:
    """口座への収入入金（家賃収入カテゴリ優先）。"""
    cfg = load_config()
    accounts = cfg.get("deposit_accounts") or {}
    matches = {
        str(v.get("bank_id")): str(v.get("zaim_match") or "")
        for v in accounts.values()
        if isinstance(v, dict)
    }
    # also ensure keys
    path = ZAIM_CSV
    # try current year file; also previous
    year = datetime.now(JST).year
    candidates = [
        TAX / f"{year}年度" / f"Zaim.{year}年度.csv",
        TAX / f"{year - 1}年度" / f"Zaim.{year - 1}年度.csv",
        ZAIM_CSV,
    ]
    csv_path = next((p for p in candidates if p.is_file()), None)
    if not csv_path:
        return []

    out: list[dict[str, Any]] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            method = (row.get("方法") or "").strip()
            if method != "income":
                continue
            try:
                income = int(float(str(row.get("収入") or "0").replace(",", "") or 0))
            except ValueError:
                income = 0
            if income <= 0:
                continue
            date = (row.get("日付") or "").replace("/", "-")[:10]
            if len(date) < 7:
                continue
            row_ym = date[:7]
            if ym and row_ym != ym:
                continue
            dep = row.get("入金先") or ""
            cat = row.get("カテゴリ") or ""
            item = row.get("品目") or ""
            bank_id = None
            for bid, match in matches.items():
                if match and match in dep:
                    bank_id = bid
                    break
            if not bank_id:
                # fallback common
                if "PayPay" in dep:
                    bank_id = "paypay"
                elif "MUFG" in dep:
                    bank_id = "mufg"
                elif "滋賀" in dep:
                    bank_id = "shiga"
                elif "京都" in dep:
                    bank_id = "kyoto"
            if not bank_id:
                continue
            is_rent = "家賃" in cat or "家賃" in item
            out.append(
                {
                    "source": "zaim_bank",
                    "ym": row_ym,
                    "bank_id": bank_id,
                    "date": date,
                    "amount_yen": income,
                    "is_rent_category": is_rent,
                    "category": cat,
                    "item": item,
                    "deposit_account": dep,
                    "label": f"Zaim {bank_id} {income:,}",
                }
            )
    return out


def aggregate_banks(inflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ym×bank の家賃カテゴリ合算（無ければ全収入合算を参考）。"""
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in inflows:
        key = (row["ym"], row["bank_id"])
        b = buckets.setdefault(
            key,
            {
                "source": "zaim_bank_aggregate",
                "ym": row["ym"],
                "bank_id": row["bank_id"],
                "rent_category_yen": 0,
                "all_income_yen": 0,
                "rent_hits": 0,
                "all_hits": 0,
                "samples": [],
            },
        )
        b["all_income_yen"] += row["amount_yen"]
        b["all_hits"] += 1
        if row.get("is_rent_category"):
            b["rent_category_yen"] += row["amount_yen"]
            b["rent_hits"] += 1
        if len(b["samples"]) < 5:
            b["samples"].append(
                {
                    "date": row["date"],
                    "amount_yen": row["amount_yen"],
                    "item": row.get("item"),
                    "is_rent": row.get("is_rent_category"),
                }
            )
    out = []
    for b in buckets.values():
        b["amount_yen"] = b["rent_category_yen"] or b["all_income_yen"]
        b["amount_basis"] = (
            "rent_category" if b["rent_category_yen"] else "all_income"
        )
        b["label"] = f"合算 {b['bank_id']} {b['ym']} {b['amount_yen']:,}"
        out.append(b)
    return out


def run_ingest(ym_filter: str | None = None) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    errors: list[str] = []

    for path in iter_leaf_pdfs():
        try:
            text = pdf_text(path)
            rows = parse_leaf(path, text)
            entries.extend(rows)
        except Exception as e:
            errors.append(f"leaf {path.name}: {e}")

    for path in iter_minitech_pdfs():
        try:
            text = pdf_text(path)
            rows = parse_minitech(path, text)
            entries.extend(rows)
        except Exception as e:
            errors.append(f"minitech {path.name}: {e}")

    for path in iter_tcell_pdfs():
        try:
            text = pdf_text(path)
            rows = parse_tcell(path, text)
            entries.extend(rows)
        except Exception as e:
            errors.append(f"tcell {path.name}: {e}")

    if ym_filter:
        entries = [e for e in entries if e.get("ym") == ym_filter]

    inflows = zaim_bank_inflows(ym_filter)
    bank_aggs = aggregate_banks(inflows)

    # dedupe room entries by source+ym+property+room (last wins)
    dedup: dict[str, dict[str, Any]] = {}
    for e in entries:
        if not e.get("ym") or not e.get("room"):
            continue
        k = f"{e.get('source')}|{e.get('ym')}|{e.get('property_id')}|{e.get('room')}"
        dedup[k] = e
    room_entries = list(dedup.values())

    payload = {
        "updated_at": now_iso(),
        "ym_filter": ym_filter,
        "room_entries": room_entries,
        "bank_aggregates": bank_aggs,
        "errors": errors,
        "counts": {
            "room": len(room_entries),
            "bank_agg": len(bank_aggs),
            "errors": len(errors),
        },
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ym", help="YYYY-MM に限定")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.status:
        if OUT_PATH.is_file():
            print(OUT_PATH.read_text(encoding="utf-8"))
        else:
            print("{}")
        return 0
    data = run_ingest(args.ym)
    c = data["counts"]
    print(
        f"# rent_deposits: room={c['room']} bank_agg={c['bank_agg']} errors={c['errors']} → {OUT_PATH}"
    )
    for e in data["errors"][:8]:
        print(f"# err: {e}", file=sys.stderr)
    # sample
    for e in data["room_entries"][:8]:
        print(
            f"  {e.get('ym')} {e.get('source')} {e.get('property_id')}-{e.get('room')} "
            f"rent={e.get('rent_yen')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
