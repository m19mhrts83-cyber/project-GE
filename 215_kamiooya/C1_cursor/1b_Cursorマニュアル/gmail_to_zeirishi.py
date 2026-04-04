#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gmail で**宛名（To）・差出人（From）・件名**のいずれかに「税理士」または「公認会計士」を含むメールを検索し、法人検討.md の
「弥生経由で届いた税理士法人のメール（Gmail取得）」セクションに、
会社別サマリーと件名でトグル表示の本文を追記する。

- to:/subject: に加え from: も指定（Gmail の to: は表示名よりアドレス向けのため、差出人表示名で漏れを防ぐ）。
- 初回: (to:税理士 OR to:公認会計士 OR subject:税理士 OR subject:公認会計士 OR from:税理士 OR from:公認会計士) newer_than:90d
- 2回目以降: 上記条件に after:YYYY/MM/DD を追加して検索
- 既存セクションをパースし、今回取得＋既存をマージしてセクション全体を再生成（上書き）

前提: 1b_Cursorマニュアル の credentials.json / token.json を使用
"""

import argparse
import base64
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_MAIL_AUTO = Path(__file__).resolve().parent.parent / "mail_automation"
if _MAIL_AUTO.is_dir() and str(_MAIL_AUTO) not in sys.path:
    sys.path.insert(0, str(_MAIL_AUTO))
try:
    from gmail_token_sync import save_token_json_and_sync
except ImportError:
    def save_token_json_and_sync(token_path, creds_json, *, log_prefix: str = "📎 Gmail token") -> None:
        Path(token_path).parent.mkdir(parents=True, exist_ok=True)
        Path(token_path).write_text(creds_json, encoding="utf-8")
from zoneinfo import ZoneInfo

import email.utils as email_utils
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

JST = ZoneInfo("Asia/Tokyo")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
ZEIRISHI_DIR = REPO_ROOT / "50_税金,確定申告" / "法人向け税理士検討"
MD_PATH = ZEIRISHI_DIR / "法人検討.md"
STATE_FILE = ZEIRISHI_DIR / ".gmail_zeirishi_last_date"
CREDENTIALS_PATH = SCRIPT_DIR / "credentials.json"
TOKEN_PATH = SCRIPT_DIR / "token.json"

from gmail_api_scopes import (
    GMAIL_SCOPES_215 as SCOPES,
    resolve_single_token_path_215,
    token_satisfies_215_scopes,
)

SECTION_HEADER = "## 弥生経由で届いた税理士法人のメール（Gmail取得）"
SUMMARY_HEADER = "### 会社別サマリー"
COMPARISON_HEADER = "### 4社の条件比較・問い合わせ時確認事項"
TOGGLE_HEADER = "### メール本文（件名で開閉）"

# 弥生で紹介された4社（表の行順）。by_company のキーに部分一致すればその表示名を使用
FOUR_OFFICES_FOR_TABLE = [
    ("竹谷亮税理士事務所", "ryo taketani"),
    ("青野公認会計士事務所", "青野公認会計士事務所"),
    ("安藤寛税理士事務所", "安藤寛税理士事務所"),
    ("税理士法人アイビス", "アイビスグループ"),
]

# サマリー抽出用キーワード（周辺の短い文を拾う）
SUMMARY_KEYWORDS = [
    "料金", "月額", "年額", "報酬", "費用", "弥生", "仕訳", "決算",
    "申告", "プラン", "税理士", "対応", "相談", "無料",
]


def load_env():
    env_path = SCRIPT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*([^#=]+)\s*=\s*(.+?)\s*$", line)
            if m:
                key, val = m.group(1).strip(), m.group(2).strip().strip("'\"")
                if val:
                    os.environ[key] = val


load_env()
credentials_path = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", CREDENTIALS_PATH))
_tp = Path(os.environ.get("GMAIL_TOKEN_PATH", TOKEN_PATH))
token_path = resolve_single_token_path_215(
    SCRIPT_DIR,
    _tp,
    explicit_via_env=bool(os.environ.get("GMAIL_TOKEN_PATH")),
)


def parse_email_body(payload):
    """メール本文を取得。multipart のネストも再帰的に探索。"""
    plain = ""
    html = ""

    def walk(p):
        nonlocal plain, html
        if not p:
            return
        if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
            try:
                plain = base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8")
            except Exception:
                pass
        elif p.get("mimeType") == "text/html" and p.get("body", {}).get("data"):
            try:
                raw = base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8")
                html = re.sub(r"<[^>]+>", "\n", raw)
                html = re.sub(r"\n+", "\n", html).strip()
            except Exception:
                pass
        else:
            for child in p.get("parts") or []:
                walk(child)

    if payload.get("body") and payload["body"].get("data"):
        try:
            plain = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
        except Exception:
            pass
    for p in payload.get("parts") or []:
        walk(p)
    return (plain or html).strip()


def parse_from_header(from_val):
    """From ヘッダから表示名とメールアドレスを取得。"""
    if not from_val or not from_val.strip():
        return "", ""
    from_val = from_val.strip()
    m = re.search(r"<([^>]+)>", from_val)
    if m:
        addr = m.group(1).strip().lower()
        name = re.sub(r"\s*<[^>]+>\s*", "", from_val).strip()
        name = name.strip('"').strip()
        return name or addr, addr
    if "@" in from_val:
        return from_val, from_val.lower()
    return from_val, ""


def company_key(display_name, email_addr):
    """会社識別用キー。表示名があればそれ、なければドメイン。"""
    if display_name and display_name.strip():
        return display_name.strip()
    if email_addr and "@" in email_addr:
        return email_addr.split("@")[-1].lower()
    return email_addr or "不明"


def format_date(dt):
    if dt.tzinfo:
        dt = dt.astimezone(JST).replace(tzinfo=None)
    return dt.strftime("%Y/%m/%d %H:%M")


def date_only_str(dt):
    if dt.tzinfo:
        dt = dt.astimezone(JST).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d")


def extract_summary_lines(body, max_lines=3):
    """本文からキーワード周辺を抜き出し、1〜3行の比較ポイントに。"""
    if not body or not body.strip():
        return []
    lines = []
    text = re.sub(r"\s+", " ", body.strip())
    for kw in SUMMARY_KEYWORDS:
        if kw not in text:
            continue
        pos = text.find(kw)
        start = max(0, pos - 20)
        end = min(len(text), pos + 60)
        snippet = text[start:end].strip()
        if snippet and snippet not in [l for l in lines]:
            lines.append(snippet)
        if len(lines) >= max_lines:
            break
    return lines[:max_lines]


def read_last_date():
    """前回取得日を読み取り。無ければ None。"""
    if not STATE_FILE.exists():
        return None
    try:
        s = STATE_FILE.read_text(encoding="utf-8").strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            return s
    except Exception:
        pass
    return None


def write_last_date(date_str):
    """実行日の日付を保存。"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(date_str + "\n", encoding="utf-8")


def authenticate():
    """Gmail API 認証。"""
    creds = None
    if token_path.exists():
        creds_data = None
        try:
            token_data = json.loads(token_path.read_text(encoding="utf-8"))
            creds_data = dict(token_data)
            if "client_id" not in creds_data and credentials_path.exists():
                cred_data = json.loads(credentials_path.read_text(encoding="utf-8"))
                client = cred_data.get("installed") or cred_data.get("web", {})
                creds_data["client_id"] = client.get("client_id")
                creds_data["client_secret"] = client.get("client_secret")
                creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
                if "access_token" in creds_data and "token" not in creds_data:
                    creds_data["token"] = creds_data["access_token"]
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
            if creds and creds_data is not None and not token_satisfies_215_scopes(creds_data):
                creds = None
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        save_token_json_and_sync(token_path, creds.to_json())
        print("token.json を保存しました。")
    return build("gmail", "v1", credentials=creds)


def fetch_messages(service, query, max_results=500):
    """Gmail で検索し、メッセージID一覧を全ページ取得。"""
    ids = []
    page_token = None
    while True:
        params = {"userId": "me", "q": query, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        result = service.users().messages().list(**params).execute()
        ids.extend([m["id"] for m in result.get("messages", [])])
        page_token = result.get("nextPageToken")
        if not page_token or len(ids) >= max_results:
            break
    return ids[:max_results]


def parse_existing_section(content):
    """
    「## 弥生経由で届いた...」セクションから <details> をパースし、
    (date_ymd, subject, company_name, body) のリストと (subject, date_ymd) のセットを返す。
    """
    section_start = content.find(SECTION_HEADER)
    if section_start == -1:
        return [], set()

    rest = content[section_start:]
    next_h2 = re.search(r"\n## (?!#)", rest)
    section = rest[: next_h2.start()] if next_h2 else rest

    entries = []
    seen = set()
    # <details><summary>YYYY/MM/DD 件名（会社名）</summary> ... </details>
    pattern = re.compile(
        r"<details>\s*<summary>([^<]+)</summary>\s*(.*?)</details>",
        re.DOTALL,
    )
    for m in pattern.finditer(section):
        summary_text = m.group(1).strip()
        body = m.group(2).strip()
        # summary は "YYYY/MM/DD 件名（会社名）" や "YYYY/MM/DD 件名" を想定
        date_ymd = ""
        subject = summary_text
        company = ""
        dm = re.match(r"^(\d{4}/\d{2}/\d{2})(?:\s+(\d{1,2}:\d{2}))?\s+(.+)$", summary_text)
        if dm:
            date_ymd = dm.group(1).replace("/", "-")
            subject = dm.group(3).strip()
            paren = re.search(r"（([^）]+)）\s*$", subject)
            if paren:
                company = paren.group(1)
                subject = re.sub(r"\s*（[^）]+）\s*$", "", subject).strip()
        else:
            dm2 = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(.+)$", summary_text)
            if dm2:
                date_ymd = dm2.group(1)
                subject = dm2.group(2).strip()
        key = (subject, date_ymd)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "date_ymd": date_ymd,
                "subject": subject,
                "company": company,
                "body": body,
                "display_name": company,
                "email": "",
            }
        )
    return entries, seen


def build_section_content(all_entries, last_fetch_date):
    """
    all_entries: list of dict with date_ymd, subject, company, body, display_name, email
    会社別にソートし、サマリー＋トグルを生成。
    """
    # 会社名でグルーピング（表示名 or ドメイン）
    by_company = defaultdict(list)
    for e in all_entries:
        name = e.get("company") or e.get("display_name") or e.get("email", "")
        if not name:
            name = "不明"
        by_company[name].append(e)

    # 日付でソート（新しい順）
    for k in by_company:
        by_company[k].sort(key=lambda x: (x.get("date_ymd") or "", x.get("subject") or ""), reverse=True)

    # 会社の表示順（最初に出現したメールの日付でソート）
    company_order = sorted(
        by_company.keys(),
        key=lambda c: min(e.get("date_ymd") or "9999" for e in by_company[c]),
    )

    lines = [
        SECTION_HEADER,
        "",
        f"最終取得: {last_fetch_date}",
        "",
        SUMMARY_HEADER,
        "",
    ]

    for company in company_order:
        emails = by_company[company]
        first = emails[0]
        from_label = first.get("email", "")
        if from_label:
            lines.append(f"#### {company}（送信元: {from_label}）")
        else:
            lines.append(f"#### {company}")
        lines.append("")
        # その会社の全メール本文からサマリーを集約
        all_bodies = " ".join(e.get("body", "") for e in emails)
        summary_lines = extract_summary_lines(all_bodies, max_lines=3)
        for sl in summary_lines:
            lines.append(f"- {sl}")
        if not summary_lines:
            lines.append("- （メール本文から自動抽出した比較ポイント）")
        lines.append("")
        lines.append("")

    # 4社の条件比較・問い合わせ時確認事項（サマリーと本文の間）
    lines.append("---")
    lines.append("")
    lines.append(COMPARISON_HEADER)
    lines.append("")
    lines.append("| 事務所名 | 法人決算・申告 | 料金体系（仕訳数連動等） | 弥生対応 | 領収書・実物の扱い | 問い合わせ時確認したいこと |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for label, key_part in FOUR_OFFICES_FOR_TABLE:
        # 表の1列目は統一ラベル（竹谷亮税理士事務所 等）で表示
        lines.append(f"| {label} |  |  |  |  |  |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(TOGGLE_HEADER)
    lines.append("")

    # 全メールを日付降順でトグル
    flat = []
    for e in all_entries:
        flat.append(e)
    flat.sort(key=lambda x: (x.get("date_ymd") or "9999", x.get("subject") or ""), reverse=True)

    for e in flat:
        date_ymd = e.get("date_ymd", "")
        subject = (e.get("subject") or "").replace("\n", " ")
        company = e.get("company") or e.get("display_name") or ""
        body = e.get("body", "")
        if len(subject) > 80:
            subject = subject[:77] + "..."
        summary_label = f"{date_ymd.replace('-', '/')} {subject}"
        if company:
            summary_label += f"（{company}）"
        # 本文内の </details> でトグルが壊れないよう置換
        body_safe = (body or "").replace("</details>", "（/details）")
        lines.append("<details>")
        lines.append(f"<summary>{summary_label}</summary>")
        lines.append("")
        lines.append(body_safe)
        lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def replace_or_insert_section(content, new_section_text):
    """法人検討.md の該当セクションを置換、または「## 関連」の直前に挿入。"""
    if SECTION_HEADER not in content:
        # 「## 関連」の直前に挿入
        marker = "\n## 関連\n"
        pos = content.find(marker)
        if pos == -1:
            return content.rstrip() + "\n\n" + new_section_text + "\n"
        return content[:pos] + "\n" + new_section_text + "\n\n" + content[pos:]
    # セクションを抜き出して置換
    start = content.find(SECTION_HEADER)
    rest = content[start:]
    next_h2 = re.search(r"\n## (?!#)", rest)
    end_of_section = start + (next_h2.start() if next_h2 else len(rest))
    before = content[:start].rstrip()
    after = content[end_of_section:].lstrip()
    return before + "\n\n" + new_section_text + "\n\n" + after


def main():
    parser = argparse.ArgumentParser(description="税理士メールをGmailから取得し法人検討.mdにまとめる")
    parser.add_argument("--dry-run", action="store_true", help="Gmail取得のみ行い、MDを更新しない")
    parser.add_argument("--full", action="store_true", help="前回日付を無視し、To/From/件名に税理士 or 公認会計士 newer_than:90d で全件取得")
    args = parser.parse_args()

    if not credentials_path.exists():
        print("エラー: credentials.json が見つかりません", file=sys.stderr)
        sys.exit(1)

    service = authenticate()

    # 宛名（To）・差出人（From）・件名のいずれかに「税理士」または「公認会計士」があれば抽出
    # to: は表示名よりアドレス向けのため、差出人表示名用に from: も含める（aono@a-aono.co.jp 等の漏れ防止）
    search_part = "(to:税理士 OR to:公認会計士 OR subject:税理士 OR subject:公認会計士 OR from:税理士 OR from:公認会計士)"
    last = None if args.full else read_last_date()
    if last:
        query = f"{search_part} after:{last.replace('-', '/')}"
        print(f"前回取得日以降を検索（To/From/件名に税理士 or 公認会計士）: {query}")
    else:
        query = f"{search_part} newer_than:90d"
        print(f"初回または90日分を検索（To/From/件名に税理士 or 公認会計士）: {query}")

    msg_ids = fetch_messages(service, query)
    print(f"該当メール: {len(msg_ids)} 件")

    new_entries = []
    for mid in msg_ids:
        full = service.users().messages().get(userId="me", id=mid, format="full").execute()
        headers = full.get("payload", {}).get("headers", [])
        from_val = next((h["value"] for h in headers if h["name"].lower() == "from"), None)
        from_date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
        display_name, email_addr = parse_from_header(from_val)
        company = company_key(display_name, email_addr)
        body = parse_email_body(full.get("payload", {}))
        if from_date:
            try:
                dt = email_utils.parsedate_to_datetime(from_date)
                date_ymd = date_only_str(dt)
                date_display = format_date(dt)
            except (TypeError, ValueError):
                dt = datetime.now(JST)
                date_ymd = date_only_str(dt)
                date_display = format_date(dt)
        else:
            dt = datetime.now(JST)
            date_ymd = date_only_str(dt)
            date_display = format_date(dt)
        new_entries.append({
            "date_ymd": date_ymd,
            "date_display": date_display,
            "subject": subject,
            "company": company,
            "display_name": display_name,
            "email": email_addr,
            "body": body,
        })

    if not MD_PATH.exists():
        print(f"警告: {MD_PATH} が見つかりません。", file=sys.stderr)
        if not args.dry_run:
            ZEIRISHI_DIR.mkdir(parents=True, exist_ok=True)
            MD_PATH.write_text("# 法人の決算・確定申告に関する検討\n\n---\n\n" + SECTION_HEADER + "\n\n（Gmail取得スクリプトで追加）\n", encoding="utf-8")

    content = MD_PATH.read_text(encoding="utf-8")
    existing_entries, seen_keys = parse_existing_section(content)

    # 新規分のみ追加（件名＋日付で重複排除）
    merged = list(existing_entries)
    for e in new_entries:
        key = (e["subject"].strip(), e["date_ymd"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append({
            "date_ymd": e["date_ymd"],
            "subject": e["subject"],
            "company": e["company"],
            "body": e["body"],
            "display_name": e["display_name"],
            "email": e["email"],
        })

    today = datetime.now(JST).strftime("%Y-%m-%d")
    new_section = build_section_content(merged, today)

    if args.dry_run:
        print("--dry-run のため法人検討.md は更新しません。")
        if new_entries:
            print("今回取得したメール件数:", len(new_entries))
        return

    new_content = replace_or_insert_section(content, new_section)
    MD_PATH.write_text(new_content, encoding="utf-8")
    write_last_date(today)
    print(f"法人検討.md を更新しました。最終取得: {today}")
    print(f"書き込み先: {MD_PATH.resolve()}")


if __name__ == "__main__":
    main()
