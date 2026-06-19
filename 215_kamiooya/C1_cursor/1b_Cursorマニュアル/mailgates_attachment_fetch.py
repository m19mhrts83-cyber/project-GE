#!/usr/bin/env python3
"""
MailGates（mgc-filelink.cybermail.jp）リンク添付を Gmail から取得し、
パートナーフォルダの 1.受信添付(Stock)/YYYY-MM-DD/ に保存する。

ミニテック林さん等は Gmail 直添付ではなく、
  1) ダウンロード URL メール
  2) 別メール [Password] でパスワード通知
の2通形式。gmail_to_yoritoori.py では本文のみ取り込み、PDF 本体は本スクリプトで取得する。

使い方:
  cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル
  export YORITOORI_BASE_PATH="$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
  export GMAIL_TOKEN_PATH=token_estate.json
  ~/selenium_env/venv/bin/python mailgates_attachment_fetch.py
  ~/selenium_env/venv/bin/python mailgates_attachment_fetch.py --partner ミニテック --days 14
  ~/selenium_env/venv/bin/python mailgates_attachment_fetch.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent.parent / "C2_ルーティン作業" / "26_パートナー社への相談"
CONTACT_YAML = BASE_DIR / "000_共通" / "連絡先一覧.yaml"
CREDENTIALS_PATH = SCRIPT_DIR / "credentials.json"
TOKEN_PATH = SCRIPT_DIR / "token.json"

from gmail_api_scopes import GMAIL_SCOPES_215 as SCOPES, token_satisfies_215_scopes
from yoritoori_utils import (
    YORITOORI_FILENAME,
    parse_received_date_folder,
    resolve_incoming_attach_date_dir,
    resolve_incoming_attach_dir,
)

MAILGATES_URL_RE = re.compile(
    r"https://mgc-filelink\.cybermail\.jp/mg-cgi/mg_att2link_auth\?k=[A-Za-z0-9]+"
)
FILE_NAME_RE = re.compile(
    r"添付ファイル\s*\(File name\):\s*(.+?)(?:\([\d.]+\s*MB\))?\s*$",
    re.MULTILINE,
)
PASSWORD_RE = re.compile(r"\[Password\]\s*\n?\s*(\S+)", re.MULTILINE)


def _load_env_token() -> Path:
    p = os.environ.get("GMAIL_TOKEN_PATH")
    if p:
        return Path(p)
    for name in ("token_estate.json", "token.json"):
        cand = SCRIPT_DIR / name
        if cand.exists():
            return cand
    return TOKEN_PATH


def _decode_body(data: str) -> str:
    raw = base64.urlsafe_b64decode(data + "==")
    for enc in ("utf-8", "cp932", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def _extract_text(payload: dict) -> str:
    texts: list[str] = []
    html_parts: list[str] = []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        if mime == "text/plain" and body.get("data"):
            texts.append(_decode_body(body["data"]))
        elif mime == "text/html" and body.get("data"):
            html_parts.append(_decode_body(body["data"]))
        for sub in part.get("parts") or []:
            walk(sub)

    walk(payload)
    plain = "\n".join(texts)
    html = "\n".join(html_parts)
    if html:
        # href 内の MailGates URL を plain に補完
        for href in re.findall(r'href="(https://mgc-filelink[^"]+)"', html, re.I):
            if href not in plain:
                plain += "\n" + href
    if not plain.strip() and html:
        plain = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
        plain = re.sub(r"<[^>]+>", " ", plain)
    return plain


def _compact_for_url_search(text: str) -> str:
    """1文字改行などで URL が分割されている本文を連結する。"""
    return re.sub(r"\s+", "", text)


def _header(headers: list, name: str) -> str:
    name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name:
            return h.get("value", "")
    return ""


def _normalize_subject(subject: str) -> str:
    s = subject.strip()
    s = re.sub(r"^\[Password\]", "", s, flags=re.I).strip()
    s = re.sub(r"^Re:\s*", "", s, flags=re.I).strip()
    return s


def _safe_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name or "attachment.pdf"


def _get_gmail_service():
    token_path = _load_env_token()
    if not token_path.exists():
        print(f"エラー: Gmail token が見つかりません: {token_path}", file=sys.stderr)
        sys.exit(1)
    token_data = json.loads(token_path.read_text(encoding="utf-8"))
    if not token_satisfies_215_scopes(token_data):
        print("エラー: Gmail token のスコープが不足しています。", file=sys.stderr)
        sys.exit(1)
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    return build("gmail", "v1", credentials=creds)


def find_partner(partners: list, name_or_folder: str):
    name_or_folder = (name_or_folder or "").strip()
    for p in partners:
        if p.get("name") == name_or_folder or p.get("folder") == name_or_folder:
            return p
    return None


def scan_mailgates_pairs(service, partner_emails: list[str], days: int) -> list[dict]:
    """リンクメールとパスワードメールを subject で突合。"""
    from_query = " OR ".join(f"from:{e}" for e in partner_emails)
    q = f"({from_query}) newer_than:{days}d"
    res = service.users().messages().list(userId="me", q=q, maxResults=100).execute()
    messages = res.get("messages") or []

    link_items: list[dict] = []
    pw_by_subject: dict[str, str] = {}

    for m in messages:
        full = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        headers = full.get("payload", {}).get("headers", [])
        subject = _header(headers, "Subject")
        date_raw = _header(headers, "Date")
        try:
            dt = parsedate_to_datetime(date_raw).astimezone()
            date_str = dt.strftime("%Y/%m/%d %H:%M")
            date_prefix = dt.strftime("%Y%m%d_%H:%M")
        except Exception:
            date_str = date_raw[:16]
            date_prefix = datetime.now().strftime("%Y%m%d_%H:%M")

        body = _extract_text(full.get("payload", {}))
        body_compact = _compact_for_url_search(body)
        norm_subj = _normalize_subject(subject)

        if subject.strip().lower().startswith("[password]"):
            m_pw = PASSWORD_RE.search(body) or PASSWORD_RE.search(body_compact)
            if m_pw:
                pw_by_subject[norm_subj] = m_pw.group(1)
            continue

        urls = MAILGATES_URL_RE.findall(body) or MAILGATES_URL_RE.findall(body_compact)
        if not urls:
            continue

        fn_match = FILE_NAME_RE.search(body) or FILE_NAME_RE.search(
            re.sub(r"(?<=[ぁ-んァ-ヶ一-龥A-Za-z0-9])\n(?=[ぁ-んァ-ヶ一-龥A-Za-z0-9])", "", body)
        )
        original_name = fn_match.group(1).strip() if fn_match else "attachment.pdf"

        link_items.append(
            {
                "message_id": m["id"],
                "subject": subject,
                "norm_subject": norm_subj,
                "date_str": date_str,
                "date_prefix": date_prefix,
                "url": urls[0],
                "original_name": original_name,
            }
        )

    pairs = []
    for item in link_items:
        password = pw_by_subject.get(item["norm_subject"], "")
        if not password:
            # 同一 thread 内の Password メールを探す
            thread = service.users().messages().get(
                userId="me", id=item["message_id"], format="minimal"
            ).execute()
            thread_id = thread.get("threadId")
            if thread_id:
                tr = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
                for tm in tr.get("messages") or []:
                    th = {h["name"].lower(): h["value"] for h in tm["payload"]["headers"]}
                    subj = th.get("subject", "")
                    if subj.strip().lower().startswith("[password]"):
                        tb = _extract_text(tm["payload"])
                        m_pw = PASSWORD_RE.search(tb)
                        if m_pw:
                            password = m_pw.group(1)
                            break
        item["password"] = password
        pairs.append(item)

    return pairs


def download_via_playwright(url: str, password: str, dest: Path) -> bool:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            pw = page.locator('input[type="password"]')
            if pw.count():
                pw.first.fill(password)
                btn = page.locator(
                    'input[type="submit"], button[type="submit"], '
                    'input[value*="OK"], button:has-text("OK"), button:has-text("ダウンロード")'
                )
                if btn.count():
                    btn.first.click()
                else:
                    page.keyboard.press("Enter")
                page.wait_for_timeout(2500)

            dl = page.locator('a[href*="att2link_download"], a:has-text("ダウンロード"), a:has-text("Download")')
            if not dl.count():
                print(f"  ❌ ダウンロードリンクが見つかりません: {url[:80]}...", file=sys.stderr)
                return False

            with page.expect_download(timeout=90000) as di:
                dl.first.click()
            download = di.value
            download.save_as(dest)
            return dest.is_file() and dest.stat().st_size > 0
        finally:
            browser.close()


def append_attachment_note(md_path: Path, date_str: str, filename: str) -> None:
    if not md_path.exists():
        return
    note = f"**添付ファイル**: {filename}（添付フォルダに保存・MailGatesリンク経由取得）"
    content = md_path.read_text(encoding="utf-8")
    if filename in content and "MailGatesリンク経由取得" in content:
        return
    marker = f"### {date_str.replace('/', '/')}"
    # date_str is YYYY/MM/DD HH:MM - find block
    short_date = date_str[:10]  # YYYY/MM/DD
    pattern = re.compile(
        rf"(### {re.escape(short_date)}[^\n]*\n[\s\S]*?)(?=\n---\n|\n### )"
    )
    m = pattern.search(content)
    if m and note not in m.group(1):
        block = m.group(1).rstrip() + "\n" + note + "\n"
        content = content[: m.start(1)] + block + content[m.end(1) :]
        md_path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="MailGates リンク添付をパートナー受信添付へ保存")
    parser.add_argument("--partner", default="ミニテック", help="連絡先 YAML の name または folder")
    parser.add_argument("--days", type=int, default=14, help="遡及日数（既定14）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base_path = Path(os.environ.get("YORITOORI_BASE_PATH", BASE_DIR))
    contact_path = base_path / "000_共通" / "連絡先一覧.yaml"
    if not contact_path.exists():
        contact_path = CONTACT_YAML

    config = yaml.safe_load(contact_path.read_text(encoding="utf-8"))
    partner = find_partner(config.get("partners", []), args.partner)
    if not partner:
        print(f"エラー: パートナー '{args.partner}' が見つかりません。", file=sys.stderr)
        sys.exit(1)

    emails = [e.lower().strip() for e in partner.get("emails", []) if e.strip()]
    if not emails:
        print(f"エラー: {partner.get('name')} にメールアドレスがありません。", file=sys.stderr)
        sys.exit(1)

    service = _get_gmail_service()
    pairs = scan_mailgates_pairs(service, emails, args.days)
    if not pairs:
        print(f"MailGates リンクメール: 0 件（直近{args.days}日・{partner.get('name')}）")
        return

    attach_root = resolve_incoming_attach_dir(base_path / partner["folder"])
    attach_root.mkdir(parents=True, exist_ok=True)
    md_path = base_path / partner["folder"] / YORITOORI_FILENAME

    ok = skip = fail = 0
    for item in pairs:
        safe = _safe_filename(item["original_name"])
        date_folder = parse_received_date_folder(item["date_str"])
        attach_dir = resolve_incoming_attach_date_dir(base_path / partner["folder"], item["date_str"])
        dest = attach_dir / f"{item['date_prefix']}_{safe}"
        rel_path = f"{date_folder}/{dest.name}"
        print(f"\n[{item['date_str']}] {item['original_name']}")
        if not item["password"]:
            print("  ⚠ パスワードメール未検出 → スキップ")
            fail += 1
            continue
        legacy_dest = attach_root / f"{item['date_prefix']}_{safe}"
        if dest.exists() or legacy_dest.exists():
            existing = dest if dest.exists() else legacy_dest
            print(f"  ⚠ 既存 → スキップ: {existing.name}")
            skip += 1
            continue
        if args.dry_run:
            print(f"  [dry-run] → {rel_path}")
            ok += 1
            continue
        if download_via_playwright(item["url"], item["password"], dest):
            print(f"  ✅ 保存: {rel_path} ({dest.stat().st_size // 1024}KB)")
            append_attachment_note(md_path, item["date_str"], rel_path)
            ok += 1
        else:
            fail += 1

    print(f"\n完了: 取得 {ok} 件, スキップ {skip} 件, 失敗 {fail} 件")


if __name__ == "__main__":
    main()
