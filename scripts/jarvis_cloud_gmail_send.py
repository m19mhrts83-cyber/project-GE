#!/usr/bin/env python3
"""
Jarvis: Cloud Agent / CI 向け Gmail 送信（対外送信前確認必須）

理想フロー:
  1) --preview で件名・宛先・本文を出す（チャットでユーザー確認）
  2) ユーザー OK 後にだけ --i-confirm-send で実送信
  3) 失敗・未配線時は Mac の yoritoori_send.py へフォールバック

  # triage 下書きのプレビュー（Supabase）
  python scripts/jarvis_cloud_gmail_send.py --from-triage ID --preview

  # 確認後の送信
  python scripts/jarvis_cloud_gmail_send.py --from-triage ID --i-confirm-send

認証（優先順）:
  GMAIL_CREDENTIALS_B64 + GMAIL_ESTATE_TOKEN_B64 または GMAIL_M19M_TOKEN_B64
  なければ 215 マニュアルの credentials.json + token_estate.json / token_m19m.json

※ Vercel Web からは呼ばない。admin token では送らない（対外 From は estate/m19m）。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
CRED_DIR = REPO / ".credentials"


def _b64_write(env_name: str, dest: Path) -> bool:
    raw = (os.environ.get(env_name) or "").strip()
    if not raw:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(raw))
    return True


def materialize_creds() -> tuple[Path, Path]:
    """(credentials.json, token.json) を返す。"""
    cred = Path(os.environ.get("GMAIL_CREDENTIALS_PATH") or "")
    tok = Path(os.environ.get("GMAIL_SEND_TOKEN_PATH") or "")
    if cred.is_file() and tok.is_file():
        return cred, tok

    cred_ci = CRED_DIR / "credentials.json"
    # 対外 From: estate 優先、次に m19m
    for env_tok, name in (
        ("GMAIL_ESTATE_TOKEN_B64", "token_estate.json"),
        ("GMAIL_M19M_TOKEN_B64", "token_m19m.json"),
    ):
        if _b64_write("GMAIL_CREDENTIALS_B64", cred_ci) or (MANUAL / "credentials.json").is_file():
            if not cred_ci.is_file() and (MANUAL / "credentials.json").is_file():
                cred_ci = MANUAL / "credentials.json"
            tok_ci = CRED_DIR / name
            if _b64_write(env_tok, tok_ci):
                return cred_ci, tok_ci
            local = MANUAL / name
            if local.is_file():
                return (cred_ci if cred_ci.is_file() else MANUAL / "credentials.json"), local

    # ローカル既定
    for name in ("token_estate.json", "token_m19m.json", "token.json"):
        p = MANUAL / name
        if p.is_file() and (MANUAL / "credentials.json").is_file():
            return MANUAL / "credentials.json", p
    raise SystemExit(
        "Gmail 送信用 credentials/token がありません。"
        " GMAIL_CREDENTIALS_B64 + GMAIL_ESTATE_TOKEN_B64（推奨）を Secrets に、"
        "または Mac の token_estate.json を用意してください。"
    )


def build_service(cred_path: Path, token_path: Path):
    sys.path.insert(0, str(MANUAL))
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    from gmail_api_scopes import GMAIL_SCOPES_215 as SCOPES

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise SystemExit(f"token 無効・再同意が必要: {token_path}")
    return build("gmail", "v1", credentials=creds)


def load_triage(item_id: str) -> dict[str, Any]:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)
    r = sb.table("triage_items").select("*").eq("id", item_id).limit(1).execute()
    rows = r.data or []
    if not rows:
        raise SystemExit(f"triage_items に id={item_id} がありません")
    return rows[0]


def preview_block(to: str, subject: str, body: str, *, sender: str, thread: str) -> str:
    return (
        "===== 送信プレビュー（まだ送っていません）=====\n"
        f"From: {sender}\n"
        f"To: {to}\n"
        f"Subject: {subject}\n"
        f"threadId: {thread or '（新規）'}\n"
        "----- 本文 -----\n"
        f"{body}\n"
        "===== ここまで =====\n"
        "ユーザー承認後: 同じ引数に --i-confirm-send を付けて再実行。\n"
    )


def send_mail(
    service,
    *,
    to: str,
    subject: str,
    body: str,
    thread_id: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    msg = MIMEText(body, _charset="utf-8")
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload: dict[str, Any] = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    if dry_run:
        return {"dry_run": True, "to": to, "subject": subject, "threadId": thread_id}
    sent = service.users().messages().send(userId="me", body=payload).execute()
    return {"id": sent.get("id"), "threadId": sent.get("threadId"), "to": to, "subject": subject}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cloud 向け Gmail 送信（確認必須）")
    ap.add_argument("--from-triage", metavar="ID", help="triage_items.id")
    ap.add_argument("--to", default="", help="宛先（triage 以外・明示）")
    ap.add_argument("--subject", default="", help="件名（triage 以外）")
    ap.add_argument("--body-file", type=Path, help="本文ファイル（triage 以外）")
    ap.add_argument("--preview", action="store_true", help="プレビューのみ（既定動作に近い）")
    ap.add_argument(
        "--i-confirm-send",
        action="store_true",
        help="ユーザーがチャットで承認したあとの実送信",
    )
    ap.add_argument("--dry-run", action="store_true", help="API まで行かず組み立てのみ")
    args = ap.parse_args(argv)

    if not args.from_triage and not (args.to and args.subject and args.body_file):
        ap.error("--from-triage か (--to + --subject + --body-file) が必要です")

    do_send = bool(args.i_confirm_send) and not args.dry_run and not args.preview
    if args.i_confirm_send and args.preview:
        ap.error("--preview と --i-confirm-send は同時指定できません")

    to = args.to
    subject = args.subject
    body = ""
    thread_id = ""
    if args.from_triage:
        it = load_triage(args.from_triage)
        body = (it.get("draft_text") or "").strip()
        if not body:
            raise SystemExit("draft_text が空です。先に下書きを埋めてください。")
        subject = subject or (it.get("subject") or "")
        if subject and not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        to = to or (it.get("from_email") or "").strip()
        thread_id = (it.get("gmail_thread_id") or "").strip()
        if not to:
            raise SystemExit("宛先 from_email が空です。--to で指定してください。")
    else:
        body = args.body_file.read_text(encoding="utf-8")
        subject = subject or "（件名なし）"

    cred_path, token_path = materialize_creds()
    service = build_service(cred_path, token_path)
    profile = service.users().getProfile(userId="me").execute()
    sender = profile.get("emailAddress") or ""

    print(preview_block(to, subject, body, sender=sender, thread=thread_id))
    if not do_send:
        print("# mode: preview/dry-run（未送信）", file=sys.stderr)
        if args.dry_run:
            print(json.dumps(send_mail(service, to=to, subject=subject, body=body, thread_id=thread_id or None, dry_run=True), ensure_ascii=False))
        return 0

    result = send_mail(
        service,
        to=to,
        subject=subject,
        body=body,
        thread_id=thread_id or None,
        dry_run=False,
    )
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    print("# sent", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
