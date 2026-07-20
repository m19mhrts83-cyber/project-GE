#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeStudy 採点自動化 — Google スプレッドシートを xlsx バックアップとして保存する。

正本は Google ドライブ上のスプレッドシート。本スクリプトは Excel 化・消失時の
立ち戻り用に OneDrive へ xlsx コピーを書き出す。

使い方:
  cd ~/git-repos/215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化
  ~/selenium_env/venv/bin/python 18_export_spreadsheet_backup.py

  # 出力先を指定
  ... --output-dir ~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WESTUDY_COMMON = SCRIPT_DIR.parent.parent / "westudy_common"
if str(WESTUDY_COMMON) not in sys.path:
    sys.path.insert(0, str(WESTUDY_COMMON))

import yaml  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.http import MediaIoBaseDownload  # noqa: E402

from google_workspace_auth import load_credentials  # noqa: E402

CONFIG_PATH = WESTUDY_COMMON / "kamiooya_google_config.yaml"
DEFAULT_OUTPUT_DIR = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化"
)
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _load_spreadsheet_id() -> str:
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"設定が見つかりません: {CONFIG_PATH}")
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    ss_id = cfg.get("saiten_spreadsheet_id", "").strip()
    if not ss_id:
        raise ValueError("kamiooya_google_config.yaml に saiten_spreadsheet_id がありません")
    return ss_id


def export_xlsx(spreadsheet_id: str, output_path: Path) -> None:
    creds = load_credentials()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    request = drive.files().export(fileId=spreadsheet_id, mimeType=XLSX_MIME)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with io.FileIO(str(output_path), "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    size_kb = output_path.stat().st_size / 1024
    print(f"✅ バックアップ保存: {output_path}")
    print(f"   サイズ: {size_kb:.1f} KB")
    print(f"   正本 SS ID: {spreadsheet_id}")
    print(f"   URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")


def main() -> int:
    parser = argparse.ArgumentParser(description="採点 SS を xlsx バックアップ")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="xlsx の保存先ディレクトリ",
    )
    parser.add_argument(
        "--filename",
        default="",
        help="ファイル名（未指定時 WeStudy_採点自動化_バックアップ_YYYYMMDD.xlsx）",
    )
    parser.add_argument(
        "--also-stable-name",
        action="store_true",
        default=True,
        help="WeStudy_採点自動化_バックアップ.xlsx にも上書きコピー（既定 ON）",
    )
    args = parser.parse_args()

    ss_id = _load_spreadsheet_id()
    stamp = dt.date.today().strftime("%Y%m%d")
    filename = args.filename or f"WeStudy_採点自動化_バックアップ_{stamp}.xlsx"
    dated_path = args.output_dir / filename

    export_xlsx(ss_id, dated_path)

    if args.also_stable_name:
        stable = args.output_dir / "WeStudy_採点自動化_バックアップ.xlsx"
        stable.write_bytes(dated_path.read_bytes())
        print(f"📎 固定名コピー: {stable}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
