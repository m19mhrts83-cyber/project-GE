#!/usr/bin/env python3
"""
保険会社等へ、Gmail API で「新規メール」（In-Reply-To なし）を送る。

- 対象フォルダの `4.送信下書き.txt`（1行目 `件名：`）と `3.送信添付` を使用する。
- 送信前に `5.やり取り.md` へ追記し、成功後に添付を「送信添付(過去)」へ移動する。
- `yoritoori_send.py`（パートナー返信）とは別ルート。

典型（311_グッドウィン）:
  宛先既定: RJS30_8080@aioinissaydowa.co.jp（あいおいニッセイ同和損保提出用）

使い方:
  export YORITOORI_BASE_PATH="…/26_パートナー社への相談"   # OneDrive 運用時は推奨
  cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル
  ~/git-repos/ProgramCode/venv_gmail/bin/python gmail_send_insurance_submit.py --relative-folder 311_グッドウィン
  ~/git-repos/ProgramCode/venv_gmail/bin/python gmail_send_insurance_submit.py --folder "/絶対パス/311_グッドウィン"
  ~/git-repos/ProgramCode/venv_gmail/bin/python gmail_send_insurance_submit.py --dry-run --skip-confirm

正本の手順・宛先: `311_グッドウィン/6_保険対応メモ_鶴見さん.md`（保険会社提出用メール）
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
_MAIL_AUTO = SCRIPT_DIR.parent / "mail_automation"
if _MAIL_AUTO.is_dir() and str(_MAIL_AUTO) not in sys.path:
    sys.path.insert(0, str(_MAIL_AUTO))
try:
    from gmail_token_sync import save_token_json_and_sync
except ImportError:
    def save_token_json_and_sync(token_path, creds_json, *, log_prefix: str = "📎 Gmail token") -> None:
        Path(token_path).parent.mkdir(parents=True, exist_ok=True)
        Path(token_path).write_text(creds_json, encoding="utf-8")

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from gmail_api_scopes import (
    GMAIL_SCOPES_215 as SCOPES,
    resolve_single_token_path_215,
    token_satisfies_215_scopes,
)

DEFAULT_AIOI_SUBMIT_TO = "RJS30_8080@aioinissaydowa.co.jp"
DEFAULT_LOG_PARTNER_NAME = "あいおいニッセイ同和損保"


def _apply_yoritoori_base_path(explicit: str | None) -> None:
    """yoritoori_send モジュールの base_path を、送信前に揃える。"""
    import yoritoori_send as ys

    base = explicit or os.environ.get("YORITOORI_BASE_PATH", "").strip()
    if base:
        ys.base_path = Path(base).resolve()


def _resolve_partner_paths(args: argparse.Namespace) -> tuple[Path, str]:
    """
    (partner_root, folder_path_relative)
    partner_root = base / folder_path の絶対パス
    """
    import yoritoori_send as ys

    if args.folder:
        root = Path(args.folder).resolve()
        if not root.is_dir():
            print(f"エラー: --folder がディレクトリではありません: {root}", file=sys.stderr)
            sys.exit(1)
        folder_path = root.name
        expected_base = root.parent.resolve()
        if ys.base_path.resolve() != expected_base:
            ys.base_path = expected_base
        return root, folder_path

    if not args.relative_folder:
        print("エラー: --folder または --relative-folder を指定してください。", file=sys.stderr)
        sys.exit(1)

    folder_path = args.relative_folder.strip().strip("/")
    root = (ys.base_path / folder_path).resolve()
    if not root.is_dir():
        print(f"エラー: パートナーフォルダが見つかりません: {root}", file=sys.stderr)
        sys.exit(1)
    return root, folder_path


def _build_new_message(to_email: str, subject: str, body_text: str, attachment_paths: list[Path]) -> str:
    msg = MIMEMultipart()
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    for path in attachment_paths:
        ctype, _ = mimetypes.guess_type(str(path))
        if ctype is None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(path, "rb") as f:
            part = MIMEBase(maintype, subtype)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        msg.attach(part)

    return base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")


def _gmail_service():
    credentials_path = SCRIPT_DIR / "credentials.json"
    token_path = resolve_single_token_path_215(
        SCRIPT_DIR,
        SCRIPT_DIR / "token.json",
        explicit_via_env=bool(os.environ.get("GMAIL_TOKEN_PATH")),
    )
    creds = None
    if token_path.exists():
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
        try:
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
            if creds and not token_satisfies_215_scopes(creds_data):
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

    return build("gmail", "v1", credentials=creds)


def main() -> None:
    parser = argparse.ArgumentParser(description="保険会社等へ新規メール（下書き＋添付）を Gmail で送信")
    parser.add_argument(
        "--relative-folder",
        default="311_グッドウィン",
        help="YORITOORI_BASE_PATH からの相対パス（既定: 311_グッドウィン）",
    )
    parser.add_argument(
        "--folder",
        default="",
        help="パートナーフォルダの絶対パス（指定時は --relative-folder より優先）",
    )
    parser.add_argument(
        "--yoritoori-base",
        default="",
        help="26_パートナー社への相談 までのパス（未指定時は環境変数 YORITOORI_BASE_PATH → git-repos 既定）",
    )
    parser.add_argument(
        "--to",
        default=DEFAULT_AIOI_SUBMIT_TO,
        help=f"宛先 To（既定: {DEFAULT_AIOI_SUBMIT_TO}）",
    )
    parser.add_argument(
        "--log-partner-name",
        default=DEFAULT_LOG_PARTNER_NAME,
        help="5.やり取り.md 追記時の相手名ラベル（既定: あいおいニッセイ同和損保）",
    )
    parser.add_argument("--dry-run", action="store_true", help="送信・追記・添付移動を行わない")
    parser.add_argument("--skip-confirm", action="store_true", help="送信前の確認プロンプトを省略")
    args = parser.parse_args()

    if args.yoritoori_base:
        os.environ["YORITOORI_BASE_PATH"] = str(Path(args.yoritoori_base).resolve())

    # yoritoori_send を import する前に YORITOORI_BASE_PATH を決める
    _apply_yoritoori_base_path(None)

    import yoritoori_send as ys
    from yoritoori_utils import DRAFT_FILENAME, resolve_attach_dir

    from yoritoori_send import (  # noqa: WPS433 (import after env)
        collect_attachment_files,
        confirm_before_send,
        move_attachments_to_past,
        parse_draft,
        trigger_editor_save_all,
    )

    partner_root, folder_path = _resolve_partner_paths(args)
    draft_path = partner_root / DRAFT_FILENAME
    if not draft_path.exists():
        print(f"エラー: {DRAFT_FILENAME} がありません: {draft_path}", file=sys.stderr)
        sys.exit(1)

    if not args.dry_run and not trigger_editor_save_all():
        print(
            "エラー: Cursor/VS Code の「すべて保存」に失敗しました。送信を中止します。",
            file=sys.stderr,
        )
        sys.exit(1)
    if not args.dry_run:
        print("送信下書きを保存しました。（Cursor/VS Code の「すべて保存」を実行）")

    subject, body_text = parse_draft(draft_path)
    if not body_text.strip():
        print("エラー: 送信下書きの本文が空です。", file=sys.stderr)
        sys.exit(1)

    attach_dir = resolve_attach_dir(partner_root)
    attachment_paths = collect_attachment_files(attach_dir)
    attachment_names = [p.name for p in attachment_paths]
    if not attachment_paths:
        print("エラー: 送信添付フォルダにファイルがありません。", file=sys.stderr)
        sys.exit(1)

    if not confirm_before_send(
        partner_name=args.log_partner_name,
        via=f"Gmail（新規・To {args.to}）",
        draft_path=draft_path,
        subject=subject or "（件名なし）",
        body_text=body_text,
        attachment_names=attachment_names,
        skip_confirm=args.skip_confirm,
        dry_run=args.dry_run,
    ):
        return

    if args.dry_run:
        print("【dry-run】送信・やり取り追記・添付移動は行いませんでした。")
        return

    ys.append_sent_to_yoritoori(
        folder_path,
        args.log_partner_name + "（保険会社宛）",
        subject or "（件名なし）",
        body_text,
        attachment_names,
    )
    print("5.やり取り.md に送信内容を追記しました。")

    raw = _build_new_message(args.to, subject or "（件名なし）", body_text, attachment_paths)
    service = _gmail_service()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"送信しました: {args.to}")

    move_attachments_to_past(attach_dir, attachment_paths)


if __name__ == "__main__":
    main()
