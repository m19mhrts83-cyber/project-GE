#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
進捗管理・課題シート（個人用）から、懇親会申請フォーム用の状況を取得する。

使い方:
  python kadai_sheet_fetch.py --for-form
  python kadai_sheet_fetch.py --json
"""

from __future__ import annotations

import argparse
import json
import re
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

    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"設定ファイルがありません: {CONFIG_PATH}")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _normalize_cell(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _sheets_service():
    creds = load_credentials()
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def fetch_koteihyo_summary(
    *,
    spreadsheet_id: str,
    sheet_name: str = "【工程表】",
) -> dict:
    """【工程表】のチェックリストから動画視聴・課題提出状況を集計。"""
    sheets = _sheets_service()
    range_a1 = f"'{sheet_name}'!A1:F300"
    values = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_a1)
        .execute()
        .get("values")
        or []
    )

    checklist_items: list[dict] = []
    for row_index, row in enumerate(values, start=1):
        row = row + [""] * 6
        no, title, _, _, status, metric = [_normalize_cell(c) for c in row[:6]]
        if not re.match(r"^[\d]", no) or not title:
            continue
        is_submission = "★" in metric or "★" in title
        checklist_items.append(
            {
                "row": row_index,
                "no": no,
                "title": title,
                "status": status,
                "is_submission": is_submission,
            }
        )

    total = len(checklist_items)
    done = [x for x in checklist_items if x["status"] == "完了"]
    pending = [x for x in checklist_items if x["status"] and x["status"] != "完了"]
    empty = [x for x in checklist_items if not x["status"]]

    submissions = [x for x in checklist_items if x["is_submission"]]
    submissions_done = [x for x in submissions if x["status"] == "完了"]

    return {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "checklist_total": total,
        "checklist_done": len(done),
        "checklist_pending": len(pending),
        "checklist_empty": len(empty),
        "submission_total": len(submissions),
        "submission_done": len(submissions_done),
        "pending_items": pending[:20],
        "empty_items": [{"no": x["no"], "title": x["title"][:60]} for x in empty[:20]],
    }


def fetch_step1_intro_filled(*, spreadsheet_id: str, sheet_name: str = "STEP1") -> bool:
    """STEP1 タブに自己紹介本文があるか（簡易判定）。"""
    sheets = _sheets_service()
    values = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A1:B20")
        .execute()
        .get("values")
        or []
    )
    blob = "\n".join(" ".join(str(c) for c in row) for row in values)
    return "年齢" in blob and "年収" in blob and len(blob) > 200


def build_form_texts(summary: dict, *, step1_intro: bool) -> dict:
    """懇親会申請フォーム用の自由記述テキスト案。"""
    done = summary["checklist_done"]
    total = summary["checklist_total"]
    sub_done = summary["submission_done"]
    sub_total = summary["submission_total"]
    empty = summary["checklist_empty"]

    if empty == 0 and done == total:
        video = f"基礎講座動画は工程表チェックリスト {total} 項目すべて視聴済み（完了）です。"
    else:
        video = (
            f"工程表チェックリスト {done}/{total} 項目が「完了」。"
            f"未記入 {empty} 項目あり（最新化作業中）。"
        )

    if sub_total and sub_done == sub_total and empty == 0:
        kadai = f"STEP1〜12 の講師確認課題（★項目 {sub_total} 件）はすべて提出・合格済みです。"
    else:
        kadai = (
            f"講師確認課題（★項目）{sub_done}/{sub_total} 件が「完了」。"
            f"工程表全体は {done}/{total} 項目完了。"
        )

    return {
        "video_status": video,
        "kadai_status": kadai,
        "step1_intro_filled": step1_intro,
        "ready_for_submit": empty == 0 and done == total and sub_done == sub_total and step1_intro,
    }


def fetch_for_form(*, spreadsheet_id: str, koteihyo_sheet: str) -> dict:
    summary = fetch_koteihyo_summary(spreadsheet_id=spreadsheet_id, sheet_name=koteihyo_sheet)
    step1 = fetch_step1_intro_filled(spreadsheet_id=spreadsheet_id)
    texts = build_form_texts(summary, step1_intro=step1)
    return {**summary, **texts}


def main() -> int:
    parser = argparse.ArgumentParser(description="課題・視聴状況をスプレッドシートから取得")
    parser.add_argument("--json", action="store_true", help="JSON 出力")
    parser.add_argument("--for-form", action="store_true", help="申請フォーム用テキストを表示")
    args = parser.parse_args()

    cfg = _load_config()
    sheet = (cfg.get("koteihyo_sheet_name") or "【工程表】").strip()
    data = fetch_for_form(
        spreadsheet_id=cfg["kadai_spreadsheet_id"],
        koteihyo_sheet=sheet,
    )

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"シート: 進捗管理・課題シート / {sheet}")
    print(f"動画チェックリスト: {data['checklist_done']}/{data['checklist_total']} 完了")
    print(f"  未記入: {data['checklist_empty']} / 未完了: {data['checklist_pending']}")
    print(f"講師確認（★）: {data['submission_done']}/{data['submission_total']} 完了")
    print(f"STEP1 自己紹介: {'記入済み' if data['step1_intro_filled'] else '要確認'}")
    print(f"申請フォーム自動入力の準備: {'OK' if data['ready_for_submit'] else '要更新（工程表を最新化）'}")

    if args.for_form or not args.json:
        print("\n--- フォーム入力案 ---")
        print(f"動画視聴状況:\n  {data['video_status']}")
        print(f"\n課題(STEP1〜12)提出状況:\n  {data['kadai_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
