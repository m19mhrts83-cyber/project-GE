#!/usr/bin/env python3
"""空室対策メール履歴から号室別 year1/year2 家賃の正本を抽出する。

正本: OneDrive 215 / C2_ルーティン作業/24_空室対策メール履歴/*.md
出力: .jarvis_state/rent_vacancy_baseline.json

  python scripts/jarvis_rent_vacancy_mail_baseline.py
  python scripts/jarvis_rent_vacancy_mail_baseline.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
OUT_PATH = STATE_DIR / "rent_vacancy_baseline.json"

ONEDRIVE_215 = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
).expanduser()
MAIL_DIR = ONEDRIVE_215 / "C2_ルーティン作業" / "24_空室対策メール履歴"
MAIL_DIR_MIRROR = REPO / "215_kamiooya" / "C2_ルーティン作業" / "24_空室対策メール履歴"

FILE_DATE_RE = re.compile(r"^(\d{6})_")
PROP_FROM_NAME_RE = re.compile(r"_G([12])_|G([12])_|志賀本通\s*([IⅠ]|II|Ⅱ)", re.I)

YEAR2_RE = re.compile(r"2年目以降[：:]\s*通常価格\s*([\d,]+)\s*円")
YEAR1_PAREN_RE = re.compile(r"キャンペーン[^\n]*?[（(]\s*([\d,]+)\s*円\s*[）)]")
BASE_RENT_RE = re.compile(r"・?\s*家賃[：:]\s*([\d,]+)\s*円")

MOVE_IN_CONFIRM_RE = re.compile(
    r"(?:([IⅠ]|II|Ⅱ)\s*)?(\d{3})\s*号室[：:]\s*"
    r"(\d{1,2})\s*月\s*(\d{1,2})\s*日[^\n]{0,40}入居",
    re.I,
)


def now_jst() -> datetime:
    return datetime.now(JST)


def yen(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(str(s).replace(",", ""))
    except ValueError:
        return None


def prop_id_from_token(tok: str | None, fname: str = "") -> str | None:
    if tok:
        t = tok.upper().replace("Ⅰ", "I").replace("Ⅱ", "II")
        if t in ("1", "I"):
            return "grandole-i"
        if t in ("2", "II"):
            return "grandole-ii"
    m = PROP_FROM_NAME_RE.search(fname)
    if m:
        g = (m.group(1) or m.group(2) or m.group(3) or "").upper()
        g = g.replace("Ⅰ", "I").replace("Ⅱ", "II")
        if g in ("1", "I"):
            return "grandole-i"
        if g in ("2", "II"):
            return "grandole-ii"
    if "_G1_" in fname or fname.startswith("G1"):
        return "grandole-i"
    if "_G2_" in fname or fname.startswith("G2"):
        return "grandole-ii"
    return None


def file_sort_key(path: Path) -> tuple[int, str]:
    m = FILE_DATE_RE.match(path.name)
    if m:
        return (int(m.group(1)), path.name)
    return (0, path.name)


def resolve_mail_dir() -> Path:
    if MAIL_DIR.is_dir():
        return MAIL_DIR
    if MAIL_DIR_MIRROR.is_dir():
        return MAIL_DIR_MIRROR
    return MAIL_DIR


def parse_rent_from_section(text: str) -> dict[str, int | None] | None:
    base = None
    m = BASE_RENT_RE.search(text)
    if m:
        base = yen(m.group(1))
    y1 = None
    m1 = YEAR1_PAREN_RE.search(text)
    if m1:
        y1 = yen(m1.group(1))
    elif base is not None and "キャンペーン" in text and (
        "4,000" in text or "4000" in text
    ):
        y1 = base - 4000
    y2 = None
    m2 = YEAR2_RE.search(text)
    if m2:
        y2 = yen(m2.group(1))
    elif base is not None:
        y2 = base
    if y1 is None and y2 is None and base is None:
        return None
    if y2 is None and base is not None:
        y2 = base
    if y1 is None and y2 is not None:
        y1 = y2 - 4000
    return {"year1_rent": y1, "year2_rent": y2, "listed_rent": base}


def extract_rooms_from_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    fname = path.name
    rows: list[dict[str, Any]] = []
    default_prop = prop_id_from_token(None, fname)

    def add_rent(pid: str | None, room: str, rents: dict[str, Any]) -> None:
        if not pid or not room:
            return
        if not rents.get("year1_rent") or not rents.get("year2_rent"):
            return
        rows.append(
            {
                "property_id": pid,
                "room": room,
                "year1_rent": rents["year1_rent"],
                "year2_rent": rents["year2_rent"],
                "listed_rent": rents.get("listed_rent"),
                "source_file": fname,
                "kind": "recruit",
            }
        )

    # 1) 【NNN号室 …募集条件】
    for m in re.finditer(
        r"【(\d{3})\s*号室[^\]]{0,60}】\s*\n([\s\S]*?)(?=\n={5,}|\n【|\Z)",
        text,
    ):
        room = m.group(1)
        body = m.group(2)
        # 訂正文「102号室ではなく105」の誤号室を除外
        if re.search(rf"{re.escape(room)}\s*号室ではなく", text):
            continue
        rents = parse_rent_from_section(body)
        if rents:
            add_rent(default_prop, room, rents)

    overview_rooms: list[tuple[str, str]] = []
    for m in re.finditer(
        r"＜\s*Grandole志賀本通\s*([IⅠ]|II|Ⅱ)\s*[—\-－]\s*(\d{3})\s*号室\s*＞",
        text,
        re.I,
    ):
        pid = prop_id_from_token(m.group(1), fname)
        if pid:
            overview_rooms.append((pid, m.group(2)))

    title_line = text.splitlines()[0] if text.splitlines() else ""
    title_rooms: list[tuple[str, str]] = []
    for m in re.finditer(
        r"(?:志賀本通\s*)?([IⅠ]|II|Ⅱ)?\s*(\d{3})\s*号室",
        title_line,
        re.I,
    ):
        pid = prop_id_from_token(m.group(1), fname) or default_prop
        if pid:
            title_rooms.append((pid, m.group(2)))

    # 2) 【募集条件】同一条件 → overview / title の号室のみ
    same = re.search(
        r"【募集条件】[^\n]*同一条件[^\n]*\n([\s\S]*?)(?=\n={5,}|\n【内見|\Z)",
        text,
    )
    if same:
        rents = parse_rent_from_section(same.group(1))
        targets = overview_rooms or title_rooms
        if rents and targets:
            for pid, room in targets:
                add_rent(pid, room, rents)

    # 3) 単室ファイルで【号室 募集条件】が取れなかったとき
    if not any(r.get("kind") == "recruit" for r in rows):
        rents = parse_rent_from_section(text)
        targets = title_rooms or overview_rooms
        if rents and targets:
            for pid, room in targets:
                add_rent(pid, room, rents)

    # 入居確定
    for m in MOVE_IN_CONFIRM_RE.finditer(text):
        pid = prop_id_from_token(m.group(1), fname) or default_prop
        if not pid:
            continue
        room = m.group(2)
        mm, dd = int(m.group(3)), int(m.group(4))
        ym = FILE_DATE_RE.match(fname)
        year = 2000 + int(ym.group(1)[:2]) if ym else now_jst().year
        try:
            move_in = f"{year}-{mm:02d}-{dd:02d}"
        except ValueError:
            continue
        rows.append(
            {
                "property_id": pid,
                "room": room,
                "move_in": move_in,
                "source_file": fname,
                "kind": "move_in_confirm",
            }
        )

    return rows


def build_baseline(mail_dir: Path) -> dict[str, Any]:
    files = sorted(
        [p for p in mail_dir.glob("*.md") if not p.name.startswith("Cursor")],
        key=file_sort_key,
        reverse=True,
    )
    units: dict[str, dict[str, Any]] = {}
    move_ins: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for path in files:
        try:
            rows = extract_rooms_from_file(path)
        except Exception as e:
            errors.append(f"{path.name}: {e}")
            continue
        for r in rows:
            key = f"{r['property_id']}|{r['room']}"
            if r.get("kind") == "move_in_confirm":
                if key not in move_ins:
                    move_ins[key] = r
                continue
            if key not in units and r.get("year1_rent") and r.get("year2_rent"):
                units[key] = {
                    "property_id": r["property_id"],
                    "room": r["room"],
                    "year1_rent": r["year1_rent"],
                    "year2_rent": r["year2_rent"],
                    "listed_rent": r.get("listed_rent"),
                    "source_file": r["source_file"],
                }

    for key, mi in move_ins.items():
        if key in units:
            units[key]["move_in"] = mi.get("move_in")
            units[key]["move_in_source"] = mi.get("source_file")
        else:
            units[key] = {
                "property_id": mi["property_id"],
                "room": mi["room"],
                "move_in": mi.get("move_in"),
                "move_in_source": mi.get("source_file"),
                "year1_rent": None,
                "year2_rent": None,
                "source_file": mi.get("source_file"),
            }

    return {
        "at": now_jst().isoformat(timespec="seconds"),
        "source_dir": str(mail_dir),
        "file_count": len(files),
        "units": list(units.values()),
        "errors": errors,
        "note": (
            "正本は空室対策メールの「通常家賃／キャンペーン入居から1年間-4000／2年目以降」。"
            "号室ごとに最新メールを採用。"
        ),
    }


def load_baseline() -> dict[str, Any]:
    if OUT_PATH.is_file():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {}


def baseline_index(data: dict[str, Any] | None = None) -> dict[tuple[str, str], dict]:
    data = data if data is not None else load_baseline()
    out: dict[tuple[str, str], dict] = {}
    for u in data.get("units") or []:
        pid, room = str(u.get("property_id") or ""), str(u.get("room") or "")
        if pid and room:
            out[(pid, room)] = u
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mail-dir", type=Path, default=None)
    args = ap.parse_args()

    mail_dir = args.mail_dir or resolve_mail_dir()
    if not mail_dir.is_dir():
        print(f"# mail dir missing: {mail_dir}", flush=True)
        return 1

    data = build_baseline(mail_dir)
    print(f"# vacancy baseline: units={len(data['units'])} files={data['file_count']}")
    for u in sorted(data["units"], key=lambda x: (x["property_id"], x["room"])):
        print(
            f"  {u['property_id']}-{u['room']}: "
            f"y1={u.get('year1_rent')} y2={u.get('year2_rent')} "
            f"move_in={u.get('move_in')} ← {u.get('source_file')}"
        )
    for e in data.get("errors") or []:
        print(f"  ! {e}")

    if not args.dry_run:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"# wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
