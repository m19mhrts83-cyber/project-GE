#!/usr/bin/env python3
"""
ミニテック4件のタスクのステータスを メンバー_進行中 に更新するスクリプト
使い方: python fix_minitech_status.py
"""

import os
import re
import sys
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
NOTION_VERSION = "2022-06-28"

PAGE_IDS = [
    "304f6bbe5a7681eda024dff3c1f25205",
    "304f6bbe5a7681ed9cafc35071d0de73",
    "304f6bbe5a768137bc48f3558bfe82a1",
    "304f6bbe5a76815b9d20dcd8e5b11ecf",
]


def load_env():
    env_path = SCRIPT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*NOTION_API_KEY\s*=\s*(.+?)\s*$", line)
            if m:
                val = m.group(1).strip().strip('"\'')
                if val:
                    os.environ["NOTION_API_KEY"] = val
                break


def main():
    load_env()
    token = os.environ.get("NOTION_API_KEY")
    if not token:
        print("エラー: NOTION_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

    for page_id in PAGE_IDS:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        body = {
            "properties": {
                "ステータス": {"status": {"name": "メンバー_進行中"}},
            },
        }

        res = requests.patch(url, headers=headers, json=body)

        if not res.ok:
            print(f"更新失敗: {page_id} {res.status_code} {res.text}", file=sys.stderr)
        else:
            print(f"更新完了: {page_id}")


if __name__ == "__main__":
    main()
