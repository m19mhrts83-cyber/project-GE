"""Excel列記号 ↔ 列番号、予算年度→1月開始列の計算。"""

from __future__ import annotations

# 2026年度予算の1月 = AK。毎年「計画+実績」の2列が右に追加される。
BASE_BUDGET_YEAR = 2026
BASE_JANUARY_COL = "AK"
COLUMNS_PER_YEAR = 2
MONTHS_PER_YEAR = 12


def col_to_num(col: str) -> int:
    """列記号 (A, AK, AM …) を 1 始まりの列番号へ。"""
    n = 0
    for ch in col.upper():
        if not ("A" <= ch <= "Z"):
            raise ValueError(f"invalid column letter: {col!r}")
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def num_to_col(num: int) -> str:
    """1 始まりの列番号を列記号へ。"""
    if num < 1:
        raise ValueError(f"column number must be >= 1: {num}")
    letters: list[str] = []
    while num:
        num, rem = divmod(num - 1, 26)
        letters.append(chr(rem + ord("A")))
    return "".join(reversed(letters))


def january_col_for_year(year: int, base_year: int = BASE_BUDGET_YEAR, base_col: str = BASE_JANUARY_COL) -> str:
    """指定年度の1月（予算計画列）の列記号を返す。"""
    offset = (year - base_year) * COLUMNS_PER_YEAR
    return num_to_col(col_to_num(base_col) + offset)


def month_cols_for_year(year: int, base_year: int = BASE_BUDGET_YEAR, base_col: str = BASE_JANUARY_COL) -> list[str]:
    """指定年度の1〜12月の列記号リスト。"""
    start = col_to_num(january_col_for_year(year, base_year, base_col))
    return [num_to_col(start + i) for i in range(MONTHS_PER_YEAR)]
