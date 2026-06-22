"""Numbers 別表「19_マンションローン・管理費〜支出計画〜」→ 法人/個人 Zaim カテゴリ。"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_NUMBERS_PATH = Path(
    "/Users/matsunomasaharu2/Library/Mobile Documents/com~apple~Numbers/Documents/Life Plan/260418_松野家FinancePlan.numbers"
)
DEFAULT_SHEET = "シングルインカム年収手取"
MANSION_TABLE = "19_マンションローン・管理費(予算山積み複雑なので別表で）〜支出計画〜"
# 別表は B〜M 列固定（1月〜12月）。本表の AK 列ずれとは独立。
MONTH_COLS = ["B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M"]
ROW_GRANDOLE_I = 22  # 5.Grandole I → 法人
ROWS_PERSONAL = (14, 31, 40)  # 4.Glandole II + 6.Caramel + 7.経費 → 個人
ZAIM_CORPORATE = "19F.賃貸経営(法人)"
ZAIM_PERSONAL = "19F.賃貸経営(個人事業)"


def _parse_amount(raw: str) -> int:
    s = (raw or "").strip()
    if not s or s in {"ERR", "missing value"}:
        return 0
    try:
        return int(round(float(s.replace(",", ""))))
    except ValueError:
        return 0


def _build_applescript(numbers_path: Path, sheet: str, table: str, rows: list[int]) -> str:
    rows_literal = "{" + ", ".join(str(r) for r in rows) + "}"
    cols_literal = "{" + ", ".join(f'"{c}"' for c in MONTH_COLS) + "}"
    return f'''
set docPath to POSIX file "{numbers_path}"
tell application "Numbers"
    open docPath
    delay 1
    set theTable to table "{table}" of sheet "{sheet}" of front document
    set out to ""
    repeat with r in {rows_literal}
        set rowLine to (r as text)
        repeat with colL in {cols_literal}
            try
                set v to value of cell (colL & r) of theTable
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


def extract_row_values(numbers_path: Path, sheet: str, table: str, rows: list[int]) -> dict[int, list[int]]:
    all_rows = sorted(set(rows))
    script = _build_applescript(numbers_path, sheet, table, all_rows)
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"AppleScript failed: {proc.stderr.strip()}")

    result: dict[int, list[int]] = {}
    for line in proc.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("|")
        row_num = int(parts[0])
        values = [_parse_amount(p) for p in parts[1:]]
        result[row_num] = values
    return result


def mansion_split_records(
    year: int,
    numbers_path: Path = DEFAULT_NUMBERS_PATH,
    sheet: str = DEFAULT_SHEET,
    table: str = MANSION_TABLE,
) -> list[dict]:
    rows_needed = [ROW_GRANDOLE_I, *ROWS_PERSONAL]
    data = extract_row_values(numbers_path, sheet, table, rows_needed)
    corp = data.get(ROW_GRANDOLE_I, [0] * 12)
    personal_monthly = [0] * 12
    for r in ROWS_PERSONAL:
        for i, val in enumerate(data.get(r, [0] * 12)):
            if i < 12:
                personal_monthly[i] += val

    records: list[dict] = []
    for month_idx in range(12):
        month = month_idx + 1
        records.append(
            {
                "year": year,
                "month": month,
                "numbers_category": "5.Grandole I (別表)",
                "category_key": ZAIM_CORPORATE,
                "amount_yen": corp[month_idx],
            }
        )
        records.append(
            {
                "year": year,
                "month": month,
                "numbers_category": "4+6+7 個人 (別表)",
                "category_key": ZAIM_PERSONAL,
                "amount_yen": personal_monthly[month_idx],
            }
        )
    return records
