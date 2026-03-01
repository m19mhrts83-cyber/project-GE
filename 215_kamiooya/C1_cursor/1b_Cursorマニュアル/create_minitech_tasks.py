#!/usr/bin/env python3
"""
ミニテック向けの4点依頼・相談を、依頼ごとにタスク分割して Notion に登録するスクリプト
各タスク本文にメールの内容詳細を記載

使い方: python create_minitech_tasks.py
前提: .env に NOTION_API_KEY を設定
"""

import os
import re
import sys
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
DATABASE_ID = "25ef6bbe5a7680adbdd1e5c378572cac"
TEAM_MEMBER_LIN = "2e5f6bbe-5a76-8074-aa19-fbc62b0abb32"
NOTION_VERSION = "2022-06-28"

COMMON = {
    "物件名": "02_Grandole志賀本通I",
    "部屋番号": "102",
    "ステータス": "メンバー_進行中",
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


def block_paragraph(text):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def block_heading2(text):
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


TASKS = [
    {
        "プロジェクト名": "202602｜募集・入居可能日を2/14からに変更",
        "children": [
            block_heading2("■ メールでの依頼内容"),
            block_paragraph(
                "原状回復工事が当初の予定より遅れており、2月13日完了予定となりました。"
            ),
            block_paragraph(
                "つきましては、募集開始日および入居可能日は2月14日からとしてご対応いただきたく存じます。"
            ),
            block_paragraph(
                "募集情報等への反映のほど、よろしくお願いいたします。"
            ),
        ],
    },
    {
        "プロジェクト名": "202602｜リアプロ掲載写真の追加（間取り・内装）",
        "children": [
            block_heading2("■ メールでの依頼内容"),
            block_paragraph(
                "リアプロに掲載されている写真につきまして、追加でアップロードいただくことは可能でしょうか。"
            ),
            block_paragraph(
                "間取り、内装への募集情報の充実を図りたく、ご対応をご検討いただけますと幸いです。"
            ),
            block_paragraph(
                "写真URL: https://38.gigafile.nu/0330-ab9ae1a546af33fb7055baf512f7beda"
            ),
        ],
    },
    {
        "プロジェクト名": "202602｜102号室の家主管理への切り替え",
        "children": [
            block_heading2("■ メールでの相談内容"),
            block_paragraph(
                "現在、102号室につきまして「家主管理」の形で管理をお願いできないかと考えております。"
            ),
            block_paragraph(
                "仲介会社より戸別管理のお話をいただいており、貴社にて102号室の家主管理への切り替えが可能かご相談させていただきたく存じます。"
            ),
        ],
    },
    {
        "プロジェクト名": "202602｜家主管理時の隣接駐車場（契約可否・賃料確認）",
        "children": [
            block_heading2("■ メールでの相談内容"),
            block_paragraph(
                "家主管理となった際、入居希望者から隣接駐車場のご利用希望がありました。隣の駐車場は引き続き契約可能でしょうか。"
            ),
            block_paragraph(
                "あわせて、以前お伺いした賃料13,200円（税込）が現在も変わっていないかご教示いただけますと幸いです。"
            ),
        ],
    },
]


def build_properties(task):
    return {
        "プロジェクト名": {"title": [{"text": {"content": task["プロジェクト名"]}}]},
        "物件名": {"select": {"name": COMMON["物件名"]}},
        "部屋番号": {"select": {"name": COMMON["部屋番号"]}},
        "ステータス": {"status": {"name": COMMON["ステータス"]}},
        "開始日": {"date": {"start": COMMON["開始日"]}},
        "不動産チーム担当": {"relation": [{"id": TEAM_MEMBER_LIN}]},
    }


def main():
    load_env()
    token = os.environ.get("NOTION_API_KEY")
    if not token:
        print("エラー: NOTION_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

    for i, task in enumerate(TASKS):
        body = {
            "parent": {"database_id": DATABASE_ID},
            "properties": build_properties(task),
            "children": task["children"],
        }

        res = requests.post(url, headers=headers, json=body)

        if not res.ok:
            print(f"タスク {i + 1} 登録失敗: {res.status_code} {res.text}", file=sys.stderr)
        else:
            data = res.json()
            print(f"タスク {i + 1} 登録完了: {task['プロジェクト名']}")
            print(f"  URL: {data.get('url') or data.get('id')}")

    print("\n4件の登録が完了しました。")


if __name__ == "__main__":
    main()
