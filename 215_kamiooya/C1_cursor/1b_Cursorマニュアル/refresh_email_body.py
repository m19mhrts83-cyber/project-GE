#!/usr/bin/env python3
"""
指定したメールの本文を再取得し、やり取り.md の該当ブロックを更新する。
使い方: python refresh_email_body.py --partner ホームプランナー --date "2026-02-12 11:07"
"""

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

# gmail_to_yoritoori と同じ設定
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent.parent / "C2_ルーティン作業" / "26_パートナー社への相談"
CONTACT_YAML = BASE_DIR / "000_共通" / "連絡先一覧.yaml"
CREDENTIALS_PATH = SCRIPT_DIR / "credentials.json"
TOKEN_PATH = SCRIPT_DIR / "token.json"

sys.path.insert(0, str(SCRIPT_DIR))
from gmail_api_scopes import GMAIL_SCOPES_215 as SCOPES, resolve_single_token_path_215
from yoritoori_utils import make_summary, YORITOORI_FILENAME
from gmail_to_yoritoori import (
    load_env,
    parse_email_body,
    format_date,
    extract_email,
)
import email.utils as email_utils
import yaml
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_env()
credentials_path = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", CREDENTIALS_PATH))
_rb = Path(os.environ.get("GMAIL_TOKEN_PATH", TOKEN_PATH))
token_path = resolve_single_token_path_215(
    SCRIPT_DIR,
    _rb,
    explicit_via_env=bool(os.environ.get("GMAIL_TOKEN_PATH")),
)
contact_path = Path(os.environ.get("CONTACT_LIST_PATH", CONTACT_YAML))
base_path = Path(os.environ.get("YORITOORI_BASE_PATH", BASE_DIR))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--partner", required=True, help="パートナー名（例: ホームプランナー）")
    parser.add_argument("--date", required=True, help="日付 例: 2026-02-12 11:07")
    args = parser.parse_args()

    config = yaml.safe_load(contact_path.read_text(encoding="utf-8"))
    partners = config.get("partners", [])
    partner = next((p for p in partners if args.partner in p.get("name", "")), None)
    if not partner:
        print(f"パートナーが見つかりません: {args.partner}", file=sys.stderr)
        sys.exit(1)

    folder_path = partner["folder"]
    partner_name = partner["name"]
    emails = [e.lower().strip() for e in partner.get("emails", [])]
    if not emails:
        print(f"{partner_name} にメールアドレスが登録されていません", file=sys.stderr)
        sys.exit(1)

    creds_data = json.loads(token_path.read_text(encoding="utf-8"))
    cred_data = json.loads(credentials_path.read_text(encoding="utf-8"))
    client = cred_data.get("installed") or cred_data.get("web", {})
    creds_data.setdefault("client_id", client.get("client_id"))
    creds_data.setdefault("client_secret", client.get("client_secret"))
    creds_data.setdefault("token_uri", "https://oauth2.googleapis.com/token")
    if "access_token" in creds_data and "token" not in creds_data:
        creds_data["token"] = creds_data["access_token"]
    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)

    service = build("gmail", "v1", credentials=creds)
    from_query = " OR ".join(f"from:{e}" for e in emails)
    from datetime import datetime, timedelta
    d = datetime.strptime(args.date[:10], "%Y-%m-%d")
    next_d = (d + timedelta(days=1)).strftime("%Y-%m-%d")
    query = f"({from_query}) after:{args.date[:10]} before:{next_d}"
    result = service.users().messages().list(userId="me", q=query, maxResults=20).execute()
    messages = result.get("messages", [])

    target_date = args.date.replace("-", "/")
    target_date_short = target_date[:10].replace("-", "/")
    found_msg = None
    found_date_str = None
    for msg in messages:
        full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
        headers = full.get("payload", {}).get("headers", [])
        from_date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)
        if not from_date:
            continue
        try:
            dt = email_utils.parsedate_to_datetime(from_date)
            date_str = format_date(dt)
        except Exception:
            continue
        if date_str == target_date or date_str.startswith(target_date_short):
            found_msg = full
            found_date_str = date_str
            break

    if not found_msg:
        print(f"該当メールが見つかりません: {args.partner} {args.date}")
        sys.exit(1)

    payload = found_msg.get("payload", {})
    body = parse_email_body(payload)
    if not body:
        print("メール本文を取得できませんでした。")
        sys.exit(1)

    md_path = base_path / folder_path / YORITOORI_FILENAME
    content = md_path.read_text(encoding="utf-8")

    summary = make_summary(body)
    date_esc = re.escape(target_date)
    # 添付ファイルあり
    pattern_with_attach = rf"(### {date_esc}｜[^\n]+)\n\n(\*\*件名\*\*:[^\n]*\n\n*)(.*?)(\n\s*\*\*添付ファイル\*\*:[^\n]+)"
    match = re.search(pattern_with_attach, content, re.DOTALL)
    if match:
        parts = match.group(1).split("｜")
        header_line = f"### {found_date_str}｜{parts[1]}｜{parts[2]}｜{summary}"
        subj = match.group(2).rstrip().replace("\n\n", "\n")
        if not subj.endswith("\n"):
            subj += "\n"
        new_block = f"{header_line}\n\n{subj}{body.strip()}\n{match.group(4)}"
        content = content[: match.start()] + new_block + content[match.end() :]
    else:
        # 添付ファイルなし（ブロック末尾は --- または次の ###）
        pattern_no_attach = rf"(### {date_esc}｜[^\n]+)\n\n(\*\*件名\*\*:[^\n]*\n\n*)(.*?)(\n\n---|\n\n### )"
        match = re.search(pattern_no_attach, content, re.DOTALL)
        if match:
            parts = match.group(1).split("｜")
            header_line = f"### {found_date_str}｜{parts[1]}｜{parts[2]}｜{summary}"
            subj = match.group(2).rstrip().replace("\n\n", "\n")
            if not subj.endswith("\n"):
                subj += "\n"
            new_block = f"{header_line}\n\n{subj}{body.strip()}{match.group(4)}"
            content = content[: match.start()] + new_block + content[match.end() :]
        else:
            print("該当ブロックが見つかりません。手動で確認してください。")
            sys.exit(1)
    md_path.write_text(content, encoding="utf-8")
    print(f"やり取りを更新しました: {partner_name} {found_date_str}（日本時刻）")


if __name__ == "__main__":
    main()
