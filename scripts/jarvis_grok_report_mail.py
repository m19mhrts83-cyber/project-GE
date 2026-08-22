#!/usr/bin/env python3
"""Grok 調査レポート → 松野エステイト Gmail へ送信（承認不要・内部パイプライン）。

使用アカウント: m19m または estate / Gmail API
宛先: matsuno.estate@gmail.com（固定）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_report_mail.py --file report.md --send
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_report_mail.py --text "$(pbpaste)" --subject '[Grok調査] 岡崎 〇〇' --send
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_report_mail.py --file report.md --preview

松野エステイト宛は対外ではないため --i-confirm-send は不要（--preview はデバッグ用）。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
DEFAULT_TO = "matsuno.estate@gmail.com"
GROK_PREFIX = "[Grok調査]"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def estate_to() -> str:
    """Grok パイプラインの正本は松野エステイト Gmail（PERSONAL_EMAIL とは別）。"""
    return DEFAULT_TO


def gmail_service(from_account: str):
    token = "token_estate.json" if from_account == "estate" else "token_m19m.json"
    path = MANUAL / token
    if not path.is_file() and from_account == "m19m":
        path = MANUAL / "token.json"
    if not path.is_file():
        raise FileNotFoundError(f"token not found: {path}")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def ensure_grok_header(body: str, report_id: str | None) -> str:
    text = body.strip()
    if "source: grok_bot" in text:
        return text
    rid = report_id or datetime.now().strftime("%Y%m%d-%H%M")
    header = (
        "---\n"
        "source: grok_bot\n"
        "bot: 物件調査\n"
        f"report_id: {rid}\n"
        "---\n\n"
    )
    return header + text


def derive_subject(body: str, subject: str | None) -> str:
    if subject and subject.strip():
        subj = subject.strip()
        if not subj.startswith(GROK_PREFIX):
            subj = f"{GROK_PREFIX} {subj}"
        return subj[:180]
    loc = ""
    for line in body.splitlines():
        m = re.match(r"^\s*[-*]\s*所在\s*[:：]\s*(.+)$", line.strip())
        if m:
            loc = m.group(1).strip()[:40]
            break
    short = loc or "物件調査"
    return f"{GROK_PREFIX} {short}"[:180]


def send_report(
    *,
    body: str,
    subject: str | None,
    from_account: str,
    to_email: str,
    preview: bool,
    dry_run: bool,
) -> dict:
    body = ensure_grok_header(body, None)
    subj = derive_subject(body, subject)
    to_email = (to_email or estate_to()).strip()
    from_acct = (from_account or "m19m").strip().lower()
    print(f"使用アカウント: {from_acct} / Gmail API → {to_email}")

    result = {
        "ok": True,
        "to": to_email,
        "subject": subj,
        "from_account": from_acct,
        "body_chars": len(body),
        "preview": preview,
        "dry_run": dry_run,
    }

    if preview or dry_run:
        print("===== Grok レポート送信プレビュー =====")
        print(f"From: {from_acct}")
        print(f"To: {to_email}")
        print(f"Subject: {subj}")
        print("--- body (先頭800字) ---")
        print(body[:800])
        if len(body) > 800:
            print("…")
        print(f"GROK_MAIL_RESULT:{json.dumps(result, ensure_ascii=False)}")
        return result

    svc = gmail_service(from_acct)
    msg = MIMEText(body, _charset="utf-8")
    msg["to"] = to_email
    msg["subject"] = subj
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    result["gmail_id"] = sent.get("id")
    result["thread_id"] = sent.get("threadId")
    print(f"📎 grok_report_mail: sent id={result.get('gmail_id')} subject={subj[:60]}")
    print(f"GROK_MAIL_RESULT:{json.dumps(result, ensure_ascii=False)}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="", help="レポート本文（Markdown）")
    ap.add_argument("--text", default="", help="本文直指定")
    ap.add_argument("--subject", default="", help="件名（省略時は所在から推定）")
    ap.add_argument("--to", default="", help="宛先（既定: PERSONAL_EMAIL / estate）")
    ap.add_argument(
        "--from-account",
        choices=["m19m", "estate"],
        default="m19m",
        help="送信 From（既定 m19m。TO は estate）",
    )
    ap.add_argument("--preview", action="store_true", help="送信せずプレビュー")
    ap.add_argument("--dry-run", action="store_true", help="API 送信なし")
    ap.add_argument(
        "--send",
        action="store_true",
        help="即送信（松野エステイト宛・承認不要）",
    )
    args = ap.parse_args()

    body = args.text.strip()
    if args.file:
        path = Path(args.file).expanduser()
        if not path.is_file():
            raise SystemExit(f"file not found: {path}")
        body = path.read_text(encoding="utf-8")
    if not body:
        ap.print_help()
        raise SystemExit(" --file または --text が必要です")

    if not args.preview and not args.send and not args.dry_run:
        print("# --send または --preview を指定してください（estate 宛は承認不要）")
        args.preview = True

    r = send_report(
        body=body,
        subject=args.subject or None,
        from_account=args.from_account,
        to_email=args.to,
        preview=args.preview and not args.send,
        dry_run=args.dry_run,
    )
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
