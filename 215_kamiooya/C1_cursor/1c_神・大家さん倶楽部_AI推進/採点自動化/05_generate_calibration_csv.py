#!/usr/bin/env python3
"""
月間MVP計算表から、人手採点付きの検証用CSVを作成する。

出力列:
- source_sheet
- row_no
- member_no
- member_name
- before_text
- content_text
- human_rule_hint (先行)
- human_score (得点)
- domain (分野)
- bank_name (金融機関)
"""

from pathlib import Path
import csv
import openpyxl


BASE = Path(
    "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/"
    "C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化"
)
SRC = BASE / "月間MVP計算表_2026年2月15日 23：59_fix.xlsx"
OUT = BASE / "05_calibration_samples.csv"


def find_content_col(headers):
    for i, h in enumerate(headers):
        if isinstance(h, str) and "表彰内容" in h:
            return i
    return None


def get_idx(headers, name):
    for i, h in enumerate(headers):
        if h == name:
            return i
    return None


def main():
    wb = openpyxl.load_workbook(SRC, data_only=True)
    rows = []

    for ws in wb.worksheets:
        values = list(ws.iter_rows(values_only=True))
        if not values:
            continue
        headers = list(values[0])

        i_member_no = get_idx(headers, "会員番号")
        i_member_name = get_idx(headers, "氏名")
        i_before = get_idx(headers, "Before")
        i_content = find_content_col(headers)
        i_rule = get_idx(headers, "先行")
        i_score = get_idx(headers, "得点")
        i_domain = get_idx(headers, "分野")
        i_bank = get_idx(headers, "金融機関")

        if i_content is None or i_score is None:
            continue

        for r, row in enumerate(values[1:], start=2):
            score = row[i_score] if i_score is not None else None
            content = row[i_content] if i_content is not None else None
            if score in (None, "") or content in (None, ""):
                continue

            rows.append(
                {
                    "source_sheet": ws.title,
                    "row_no": r,
                    "member_no": row[i_member_no] if i_member_no is not None else "",
                    "member_name": row[i_member_name] if i_member_name is not None else "",
                    "before_text": row[i_before] if i_before is not None else "",
                    "content_text": content,
                    "human_rule_hint": row[i_rule] if i_rule is not None else "",
                    "human_score": score,
                    "domain": row[i_domain] if i_domain is not None else "",
                    "bank_name": row[i_bank] if i_bank is not None else "",
                }
            )

    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_sheet",
                "row_no",
                "member_no",
                "member_name",
                "before_text",
                "content_text",
                "human_rule_hint",
                "human_score",
                "domain",
                "bank_name",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote: {OUT}")
    print(f"rows: {len(rows)}")


if __name__ == "__main__":
    main()

