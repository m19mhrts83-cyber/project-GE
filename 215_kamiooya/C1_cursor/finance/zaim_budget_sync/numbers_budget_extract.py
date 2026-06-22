#!/usr/bin/env python3
"""Apple Numbers 予算表 → 中間 CSV (year, month, category_key, amount_yen)。"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

import yaml

from column_utils import month_cols_for_year
from mansion_budget_split import mansion_split_records

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_NUMBERS_PATH = Path(
    "/Users/matsunomasaharu2/Library/Mobile Documents/com~apple~Numbers/Documents/Life Plan/260418_松野家FinancePlan.numbers"
)
DEFAULT_MAP_PATH = SCRIPT_DIR / "budget_category_map.yaml"
DEFAULT_SHEET = "シングルインカム年収手取"
DEFAULT_TABLE = "表1.月別予算設定"
CATEGORY_COL = "B"
DATA_START_ROW = 2


def load_mapping(map_path: Path) -> tuple[dict[str, str], list[str]]:
    data = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    exact = {m["numbers"]: m["zaim"] for m in data.get("mappings", [])}
    skip_patterns = list(data.get("skip_patterns", []))
    return exact, skip_patterns


def normalize_numbers_label(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def resolve_zaim_category(label: str, exact: dict[str, str], skip_patterns: list[str]) -> str | None:
    label = normalize_numbers_label(label)
    if not label:
        return None
    for pat in skip_patterns:
        if pat in label:
            return None
    if label in exact:
        return exact[label]
    # 表記ゆれ: 先頭数字+ピリオド付きラベルを部分一致
    for numbers_key, zaim in exact.items():
        if numbers_key in label or label in numbers_key:
            return zaim
    return None


def parse_amount(raw: str) -> int | None:
    s = (raw or "").strip()
    if not s or s in {"ERR", "missing value"}:
        return None
    try:
        return int(round(float(s.replace(",", ""))))
    except ValueError:
        return None


def build_applescript(numbers_path: Path, sheet: str, table: str, month_cols: list[str]) -> str:
    cols_literal = "{" + ", ".join(f'"{c}"' for c in month_cols) + "}"
    return f'''
set docPath to POSIX file "{numbers_path}"
tell application "Numbers"
    open docPath
    delay 1
    set theDoc to front document
    set theSheet to sheet "{sheet}" of theDoc
    set theTable to table "{table}" of theSheet
    set rowCount to row count of theTable
    set out to "ROW|" & rowCount & "\\n"
    repeat with r from {DATA_START_ROW} to rowCount
        set catCell to cell ("{CATEGORY_COL}" & (r as text)) of theTable
        try
            set catVal to value of catCell as text
        on error
            set catVal to ""
        end try
        set rowLine to (r as text) & "|" & catVal
        repeat with colL in {cols_literal}
            set c to cell (colL & (r as text)) of theTable
            try
                set v to value of c
                if v is missing value then
                    set t to ""
                else
                    set t to v as text
                end if
            on error
                set t to ""
            end try
            set rowLine to rowLine & "|" & t
        end repeat
        set out to out & rowLine & "\\n"
    end repeat
    return out
end tell
'''


def extract_raw_table(numbers_path: Path, sheet: str, table: str, month_cols: list[str]) -> list[tuple[int, str, list[str]]]:
    script = build_applescript(numbers_path, sheet, table, month_cols)
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"AppleScript failed: {proc.stderr.strip()}")

    lines = [ln for ln in proc.stdout.strip().splitlines() if ln]
    if not lines or not lines[0].startswith("ROW|"):
        raise RuntimeError("unexpected AppleScript output")

    rows: list[tuple[int, str, list[str]]] = []
    for line in lines[1:]:
        parts = line.split("|")
        row_num = int(parts[0])
        category = parts[1]
        values = parts[2:]
        rows.append((row_num, category, values))
    return rows


def rows_to_budget_records(
    raw_rows: list[tuple[int, str, list[str]]],
    year: int,
    exact: dict[str, str],
    skip_patterns: list[str],
) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    unmapped: list[str] = []

    for _row_num, category_raw, values in raw_rows:
        zaim = resolve_zaim_category(category_raw, exact, skip_patterns)
        if zaim is None:
            if normalize_numbers_label(category_raw):
                unmapped.append(normalize_numbers_label(category_raw))
            continue
        for month_idx, raw_val in enumerate(values, start=1):
            amount = parse_amount(raw_val)
            if amount is None:
                continue
            records.append(
                {
                    "year": year,
                    "month": month_idx,
                    "numbers_category": normalize_numbers_label(category_raw),
                    "category_key": zaim,
                    "amount_yen": amount,
                }
            )
    return records, unmapped


def write_csv(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["year", "month", "numbers_category", "category_key", "amount_yen"]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Numbers 予算表 → 中間 CSV")
    parser.add_argument("--year", type=int, default=2026, help="予算年度（2026 なら 1月=AK）")
    parser.add_argument("--numbers", type=Path, default=DEFAULT_NUMBERS_PATH)
    parser.add_argument("--sheet", default=DEFAULT_SHEET)
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="出力 CSV（未指定時: 同ディレクトリ budget_YYYY.csv）",
    )
    args = parser.parse_args(argv)

    month_cols = month_cols_for_year(args.year)
    print(f"📎 {args.year}年度: 1月={month_cols[0]} … 12月={month_cols[11]}")

    exact, skip_patterns = load_mapping(args.map)
    raw = extract_raw_table(args.numbers, args.sheet, args.table, month_cols)
    records, unmapped = rows_to_budget_records(raw, args.year, exact, skip_patterns)
    records.extend(mansion_split_records(args.year, args.numbers, args.sheet))

    out_path = args.output or (SCRIPT_DIR / f"budget_{args.year}.csv")
    write_csv(records, out_path)

    print(f"✅ {len(records)} 行を書き出し: {out_path}")
    if unmapped:
        unique = sorted(set(unmapped))
        print(f"⚠️  マッピング対象外（{len(unique)} 件）: {', '.join(unique[:8])}{'…' if len(unique) > 8 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
