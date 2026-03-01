#!/usr/bin/env python3
"""
Notion「所有物件タスク管理(共有)」にタスクを登録するスクリプト
MCP の parent 文字列化バグ時の代替手段

使い方:
  1. .env に NOTION_API_KEY=secret_xxxx を記述（このスクリプトと同じフォルダ）
  2. python create_notion_task.py
  または: export NOTION_API_KEY="secret_xxxx" してから実行
"""

import os
import re
import sys
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
DATABASE_ID = "25ef6bbe5a7680adbdd1e5c378572cac"
NOTION_VERSION = "2022-06-28"

TASK = {
    "プロジェクト名": "202602｜4点の依頼・相談（募集2/14から、リアプロ写真、家主管理、隣接駐車場）",
    "物件名": "01_Grandole志賀本通II",
    "部屋番号": "102",
    "ステータス": "オーナー_進行中",
    "開始日": "2026-02-11",
}


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


def build_properties(task):
    return {
        "プロジェクト名": {"title": [{"text": {"content": task["プロジェクト名"]}}]},
        "物件名": {"select": {"name": task["物件名"]}},
        "部屋番号": {"select": {"name": task["部屋番号"]}},
        "ステータス": {"status": {"name": task["ステータス"]}},
        "開始日": {"date": {"start": task["開始日"]}},
    }


def main():
    load_env()
    token = os.environ.get("NOTION_API_KEY")
    if not token:
        print("エラー: NOTION_API_KEY が設定されていません", file=sys.stderr)
        print("", file=sys.stderr)
        print("【設定方法】", file=sys.stderr)
        print("  1. https://www.notion.so/my-integrations で Integration を作成", file=sys.stderr)
        print("  2. 所有物件タスク管理(共有) を開き、「…」→「コネクト」で Integration を接続", file=sys.stderr)
        print("  3. このフォルダに .env を作成し、1行だけ記述:", file=sys.stderr)
        print("     NOTION_API_KEY=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", file=sys.stderr)
        print("  4. 再度 python create_notion_task.py を実行", file=sys.stderr)
        sys.exit(1)

    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    body = {
        "parent": {"database_id": DATABASE_ID},
        "properties": build_properties(TASK),
    }

    res = requests.post(url, headers=headers, json=body)

    if not res.ok:
        print(f"API エラー: {res.status_code} {res.text}", file=sys.stderr)
        sys.exit(1)

    data = res.json()
    print("登録完了:", data.get("url") or data.get("id"))


if __name__ == "__main__":
    main()
