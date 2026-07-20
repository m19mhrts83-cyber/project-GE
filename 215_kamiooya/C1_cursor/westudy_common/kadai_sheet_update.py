#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""【工程表】の担当・期日・状況列を一括更新（Sheets API）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from googleapiclient.discovery import build

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from google_workspace_auth import load_credentials

CONFIG_PATH = SCRIPT_DIR / "kamiooya_google_config.yaml"


def _load_config() -> dict:
    import yaml

    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _cell(values: list[list], row: int, col: int) -> str:
    if row - 1 >= len(values):
        return ""
    r = values[row - 1]
    if col >= len(r):
        return ""
    return str(r[col]).strip()


def apply_updates(
    *,
    spreadsheet_id: str,
    sheet_name: str,
    date_text: str,
    row_c_from: int,
    row_de_from: int,
    dry_run: bool = False,
) -> dict:
    creds = load_credentials()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

    values = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A1:E500")
        .execute()
        .get("values")
        or []
    )
    max_row = len(values)

    data: list[dict] = []
    for row in range(row_c_from, max_row + 1):
        if not _cell(values, row, 2):
            data.append({"range": f"'{sheet_name}'!C{row}", "values": [["松野"]]})

    for row in range(row_de_from, max_row + 1):
        if not _cell(values, row, 3):
            data.append({"range": f"'{sheet_name}'!D{row}", "values": [[date_text]]})
        if not _cell(values, row, 4):
            data.append({"range": f"'{sheet_name}'!E{row}", "values": [["完了"]]})

    summary = {
        "sheet_name": sheet_name,
        "max_row": max_row,
        "cells_to_update": len(data),
        "dry_run": dry_run,
    }

    if dry_run:
        summary["sample"] = data[:5]
        return summary

    if not data:
        return summary

    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="工程表 C/D/E 列の一括入力")
    parser.add_argument("--date", default="6/24", help="期日（既定 6/24）")
    parser.add_argument("--row-c-from", type=int, default=103)
    parser.add_argument("--row-de-from", type=int, default=73)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-reauth", action="store_true")
    args = parser.parse_args()

    if args.force_reauth:
        load_credentials(force_reauth=True)

    cfg = _load_config()
    sheet = (cfg.get("koteihyo_sheet_name") or "【工程表】").strip()

    try:
        result = apply_updates(
            spreadsheet_id=cfg["kadai_spreadsheet_id"],
            sheet_name=sheet,
            date_text=args.date,
            row_c_from=args.row_c_from,
            row_de_from=args.row_de_from,
            dry_run=args.dry_run,
        )
    except Exception as e:
        err = str(e)
        if "insufficientPermissions" in err or "403" in err:
            print(
                "書込権限がありません。次を実行して再同意してください:\n"
                "  google_workspace_setup.py --force-reauth",
                file=sys.stderr,
            )
        raise

    print(f"シート: {result['sheet_name']}")
    print(f"更新セル数: {result['cells_to_update']}" + (" (dry-run)" if result["dry_run"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
