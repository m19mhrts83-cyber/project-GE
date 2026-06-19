#!/usr/bin/env python3
"""Gmail 集約（転送確認）の補助。admin@ の未承認転送リンクを表示・ブラウザで開く。"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from gmail_api_scopes import GMAIL_SCOPES_215 as SCOPES

SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN = Path(__file__).resolve().parent / "token_livingsupport.json"


def _service():
    d = json.loads(TOKEN.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(d, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def _extract_body(payload: dict) -> str:
    chunks: list[str] = []
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        chunks.append(
            base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode("utf-8", "replace")
        )
    for c in payload.get("parts", []) or []:
        chunks.append(_extract_body(c))
    return "\n".join(chunks)


def _forward_links(svc) -> list[tuple[str, str]]:
    res = svc.users().messages().list(
        userId="me",
        q='subject:("Gmail の転送の確認") newer_than:90d',
        maxResults=20,
    ).execute()
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in res.get("messages", []) or []:
        full = svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
        hs = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
        subj = hs.get("Subject", "")
        body = _extract_body(full.get("payload", {}))
        for link in re.findall(r"https://mail-settings\.google\.com/mail/vf-[^\s<>\"]+", body):
            if link not in seen:
                seen.add(link)
                out.append((subj, link))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Gmail 転送確認リンクの表示・ブラウザ起動")
    parser.add_argument("--show-forward-links", action="store_true", help="未処理の転送確認リンクを表示")
    parser.add_argument("--open-forward-links", action="store_true", help="リンクを macOS の open で開く")
    args = parser.parse_args()
    if not args.show_forward_links and not args.open_forward_links:
        parser.print_help()
        sys.exit(0)

    if not TOKEN.is_file():
        print(f"エラー: {TOKEN} がありません", file=sys.stderr)
        sys.exit(1)

    svc = _service()
    links = _forward_links(svc)
    if not links:
        print("直近90日に「Gmail の転送の確認」メールは見つかりませんでした。")
        return

    print(f"転送確認メール: {len(links)} 件")
    for subj, link in links:
        print(f"\n件名: {subj}\n{link}")
        if args.open_forward_links and sys.platform == "darwin":
            subprocess.run(["open", link], check=False)


if __name__ == "__main__":
    main()
