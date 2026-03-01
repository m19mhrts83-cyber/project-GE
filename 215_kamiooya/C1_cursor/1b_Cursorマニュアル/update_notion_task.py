#!/usr/bin/env python3
"""
Notion ページのプロパティを更新するスクリプト
使い方: python update_notion_task.py [page_id]
"""

import os
import re
import sys
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
NOTION_VERSION = "2022-06-28"

DEFAULT_PAGE_ID = "304f6bbe5a76817fb66fdb9f408e8ad3"


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

    page_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PAGE_ID

    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    body = {
        "properties": {
            "物件名": {"select": {"name": "02-GRANDOR-4GAHONDOR-1"}},
            "不動産チーム担当": {"relation": [{"id": "2e5f6bbe-5a76-8074-aa19-fbc62b0abb32"}]},
        },
    }

    res = requests.patch(url, headers=headers, json=body)

    if not res.ok:
        print(f"API エラー: {res.status_code} {res.text}", file=sys.stderr)
        sys.exit(1)

    data = res.json()
    print("更新完了:", data.get("url") or data.get("id"))


if __name__ == "__main__":
    main()
