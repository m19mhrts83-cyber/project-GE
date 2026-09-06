#!/usr/bin/env python3
"""
Grandole志賀本通Ⅰ 201号室 エアコン故障・修理フォローチェッカー。

マルショウ石井様（naocafe398400@gmail.com）、ミニテック林様（tomoki-hayashi@minitech.co.jp）
からの新着返信を検知し、.jarvis_state/grandole_201_aircon.json のステータスを更新する。

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_grandole_201_aircon_check.py
  python scripts/jarvis_grandole_201_aircon_check.py --push
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "grandole_201_aircon.json"
MANUAL_DIR = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
sys.path.insert(0, str(MANUAL_DIR))

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

JST = ZoneInfo("Asia/Tokyo")

# 送信完了基準時刻 (2026-09-06 14:40:00 JST 以降の新着を検知)
BASE_TIMESTAMP_SEC = int(datetime.datetime(2026, 9, 6, 14, 40, tzinfo=JST).timestamp())

TARGET_SENDERS = [
    ("naocafe398400@gmail.com", "マルショウ 石井章示 様"),
    ("tomoki-hayashi@minitech.co.jp", "ミニテック 林 友貴 様"),
]


def load_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.datetime.now(JST).isoformat()
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_gmail_replies() -> list[dict]:
    tok_path = MANUAL_DIR / "token_estate.json"
    if not tok_path.is_file():
        print(f"Error: {tok_path} が見つかりません。", file=sys.stderr)
        return []

    creds = Credentials.from_authorized_user_file(str(tok_path))
    service = build("gmail", "v1", credentials=creds)

    query = f"(from:naocafe398400@gmail.com OR from:tomoki-hayashi@minitech.co.jp) after:{BASE_TIMESTAMP_SEC}"
    res = service.users().messages().list(userId="me", q=query).execute()
    messages = res.get("messages", [])

    replies = []
    for m in messages:
        mid = m.get("id")
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=mid,
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            )
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        from_hdr = headers.get("From", "")
        # 自分からの送信は除外
        if "matsuno.estate@gmail.com" in from_hdr:
            continue
        replies.append({
            "id": mid,
            "subject": headers.get("Subject", ""),
            "from": from_hdr,
            "date": headers.get("Date", ""),
        })

    return replies


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--push", action="store_true", help="状況ウォッチへ反映して Supabase へ push")
    args = parser.parse_args()

    state = load_state()
    replies = check_gmail_replies()

    print("📎 志賀本通Ⅰ 201 エアコン故障・修理フォロー確認")
    print(f"- 現在のステータス: {state.get('status', 'unknown')}")
    print(f"- 監視対象: マルショウ石井様 (naocafe398400@gmail.com) / ミニテック林様 (tomoki-hayashi@minitech.co.jp)")

    if replies:
        print(f"\n🚨 【至急】新着返信が {len(replies)} 件届いています！")
        for r in replies:
            print(f"  · [{r['date']}] {r['from']} | 件名: {r['subject']}")
        state["status"] = "reply_received"
        state["latest_replies"] = replies
        save_state(state)
    else:
        print("\n✅ 現在、先方からの新着返信はまだありません。（返信待ち継続中）")

    if args.push:
        import subprocess

        cmd = [sys.executable, str(REPO / "scripts" / "jarvis_dashboard_push.py"), "--watch-only"]
        subprocess.run(cmd, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
