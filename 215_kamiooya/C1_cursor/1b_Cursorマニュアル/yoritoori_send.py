#!/usr/bin/env python3
"""
送信下書き.txt を読み取り、パートナーに送信する。
- emails あり: Gmail 返信として送信（送信添付フォルダのファイルを添付可）
- phones のみ: iMessage 送信（送信添付フォルダのファイルを添付可）

送信前にやり取り.md へ送信内容を追記してから送信する（誤送信時も何を送ろうとしたか残る）。送信成功後、送信添付フォルダのファイルは「送信添付(過去)」へ移動する。

前提:
  - メール送信時: Gmail API 設定済み（credentials.json, token.json）、gmail.send スコープ
  - iMessage 送信時: Mac で Messages が有効、自動化の許可が必要
  - Mac の場合: 送信前に Cursor/VS Code で「すべて保存」を自動実行します。初回は「ターミナル（または Cursor）が Cursor を制御することを許可しますか？」と出たら「許可」が必要です（システム環境設定 → セキュリティとプライバシー → プライバシー → アクセシビリティ or 自動化）。

使い方:
  python yoritoori_send.py --partner 立木       # phones のみ → iMessage
  python yoritoori_send.py --partner ミニテック  # emails あり → Gmail 返信
  python yoritoori_send.py --partner LEAF --via gmail
  python yoritoori_send.py --partner LEAF --via imessage
  python yoritoori_send.py --partner 立木 --dry-run
  python yoritoori_send.py --partner LEAF --via imessage --skip-confirm
  python yoritoori_send.py --partner ミニテック --skip-chrline   # 送信前の CHRLINE 確認を省略

  送信が確定した直後（確認プロンプト承認後）、既定で CHRLINE のセッションを軽く確認する。
  保存トークンが有効なら QR は出ない。切れているときだけこのタイミングで QR 再認証が始まる。
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Optional

_MAIL_AUTO = Path(__file__).resolve().parent.parent / "mail_automation"
if _MAIL_AUTO.is_dir() and str(_MAIL_AUTO) not in sys.path:
    sys.path.insert(0, str(_MAIL_AUTO))
try:
    from gmail_token_sync import save_token_json_and_sync
except ImportError:
    def save_token_json_and_sync(token_path, creds_json, *, log_prefix: str = "📎 Gmail token") -> None:
        Path(token_path).parent.mkdir(parents=True, exist_ok=True)
        Path(token_path).write_text(creds_json, encoding="utf-8")

import yaml
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from yoritoori_utils import (
    DRAFT_FILENAME,
    YORITOORI_FILENAME,
    make_summary,
    resolve_attach_dir,
    resolve_past_attach_dir,
)

# 設定（gmail_to_yoritoori.py と共通）
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent.parent / "C2_ルーティン作業" / "26_パートナー社への相談"
CONTACT_YAML = BASE_DIR / "000_共通" / "連絡先一覧.yaml"
CREDENTIALS_PATH = SCRIPT_DIR / "credentials.json"
TOKEN_PATH = SCRIPT_DIR / "token.json"

from gmail_api_scopes import (
    GMAIL_SCOPES_215 as SCOPES,
    resolve_single_token_path_215,
    token_satisfies_215_scopes,
)


def trigger_editor_save_all():
    """
    Cursor / VS Code で「すべて保存」を実行し、未保存の送信下書きをディスクに書き込む。
    Mac のみ。送信前に必ず呼び、黒丸（未保存）のまま送るミスを防ぐ。
    """
    if sys.platform != "darwin":
        return True
    import time

    # 可能な限り「メニューから Save All」を叩く（キー割り当て変更の影響を受けにくい）
    # それが無理なら Cmd+Option+S（VS Code/Cursor のデフォルト Save All）を試す
    script = r"""
    on trySaveAll(appName)
        tell application "System Events"
            if not (exists process appName) then return false
            tell process appName
                set frontmost to true
                delay 0.3
                try
                    click menu item "Save All" of menu "File" of menu bar 1
                    return true
                on error
                end try
                try
                    click menu item "すべてを保存" of menu "ファイル" of menu bar 1
                    return true
                on error
                end try
                -- fallback: keystroke
                try
                    keystroke "s" using {command down, option down}
                    return true
                on error
                    return false
                end try
            end tell
        end tell
    end trySaveAll

    set ok to my trySaveAll("Cursor")
    if ok is false then
        set ok to my trySaveAll("Code")
    end if
    return ok
    """
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=8)
        time.sleep(1.0)
        return result.returncode == 0 and (result.stdout or "").strip().lower() != "false"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def load_env():
    env_path = SCRIPT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*([^#=]+)\s*=\s*(.+?)\s*$", line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip().strip("'\"")
                if val:
                    os.environ[key] = val


load_env()


def _find_repo_root_with_line_poc() -> Optional[Path]:
    """215 のマニュアルから git-repos 直下などをたどり、line_unofficial_poc があるルートを返す。"""
    p = SCRIPT_DIR.resolve()
    for _ in range(8):
        cand = p / "line_unofficial_poc"
        if cand.is_dir():
            return p
        if p.parent == p:
            break
        p = p.parent
    return None


def ensure_chrline_session_before_partner_send() -> None:
    """
    パートナー送信直前に CHRLINE セッションを確保する。
    保存トークンが有効なら即戻る（QRなし）。切れているときだけ requestSQR3 が動く。
    無効化: --skip-chrline または環境変数 YORITOORI_SKIP_CHRLINE=1
    """
    if os.environ.get("YORITOORI_SKIP_CHRLINE", "").strip().lower() in ("1", "true", "yes", "on"):
        return
    root = _find_repo_root_with_line_poc()
    if not root:
        print(
            "（CHRLINE: リポジトリ内に line_unofficial_poc が見つからないため、セッション確認をスキップします）",
            file=sys.stderr,
        )
        return
    poc = root / "line_unofficial_poc"
    venv_py = poc / ".venv" / "bin" / "python"
    if not venv_py.is_file():
        print(
            "（CHRLINE: line_unofficial_poc/.venv が無いため、セッション確認をスキップします）",
            file=sys.stderr,
        )
        return
    code = (
        "from chrline_client_utils import save_root_from_env, build_logged_in_client\n"
        "p = save_root_from_env()\n"
        "build_logged_in_client(p)\n"
        "print('[CHRLINE] セッション利用可能')\n"
    )
    r = subprocess.run(
        [str(venv_py), "-c", code],
        cwd=str(poc),
        text=True,
    )
    if r.returncode != 0:
        print(
            "エラー: CHRLINE（LINE 非公式）のログインに失敗しました。"
            "ターミナルで line_unofficial_poc をカレントに chrline_qr_login_poc.py を実行し、"
            "QR 認証後にもう一度お試しください。",
            file=sys.stderr,
        )
        sys.exit(1)


credentials_path = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", CREDENTIALS_PATH))
_token_default = Path(os.environ.get("GMAIL_TOKEN_PATH", TOKEN_PATH))
token_path = resolve_single_token_path_215(
    SCRIPT_DIR,
    _token_default,
    explicit_via_env=bool(os.environ.get("GMAIL_TOKEN_PATH")),
)
contact_path = Path(os.environ.get("CONTACT_LIST_PATH", CONTACT_YAML))
base_path = Path(os.environ.get("YORITOORI_BASE_PATH", BASE_DIR))


def parse_draft(draft_path):
    """送信下書き.txt をパースして (subject, body) を返す。"""
    content = draft_path.read_text(encoding="utf-8")
    lines = content.strip().split("\n")
    subject = ""
    body_lines = []

    for i, line in enumerate(lines):
        if i == 0 and re.match(r"^件名[：:]\s*(.*)$", line):
            m = re.match(r"^件名[：:]\s*(.*)$", line)
            subject = (m.group(1) or "").strip()
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    return subject, body


def _file_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def confirm_before_send(
    partner_name: str,
    via: str,
    draft_path: Path,
    subject: str,
    body_text: str,
    attachment_names: list,
    skip_confirm: bool,
    dry_run: bool,
):
    """
    送信前に、実際にディスク上にある下書き内容をプレビューして確認を取る。
    - dry-run: ここで終了（送信しない）
    - skip_confirm: 何も聞かずに続行（軌道に乗ったら運用で使う）
    """
    try:
        mtime = datetime.fromtimestamp(draft_path.stat().st_mtime).strftime("%Y/%m/%d %H:%M:%S")
        digest = _file_digest(draft_path)[:12]
    except Exception:
        mtime = "不明"
        digest = "不明"

    preview_subject = subject if subject else ""
    preview_head = body_text[:600]
    if len(body_text) > 600:
        preview_head += "\n...(以下省略)..."

    print("")
    print("========== 送信前プレビュー ==========")
    print(f"  宛先: {partner_name}")
    print(f"  手段: {via}")
    print(f"  下書き: {draft_path}")
    print(f"  更新日時: {mtime}")
    print(f"  内容ハッシュ: {digest}")
    if attachment_names:
        print(f"  添付: {attachment_names}")
    if preview_subject:
        print(f"  件名: {preview_subject}")
    print("  本文（先頭）:")
    print("------------------------------------")
    print(preview_head)
    print("------------------------------------")

    if dry_run:
        print("【dry-run】送信しません。")
        return False

    if skip_confirm:
        print("（--skip-confirm 指定のため確認なしで送信を継続します）")
        return True

    if sys.stdin is None or not sys.stdin.isatty():
        print(
            "エラー: 対話入力できない環境のため、送信前確認ができません。"
            "誤送信防止のため送信を中止します。"
            "（どうしても送る場合は --skip-confirm を指定）",
            file=sys.stderr,
        )
        sys.exit(1)

    while True:
        ans = input("この内容で送信しますか？ (y/N): ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("", "n", "no"):
            print("送信を中止しました。")
            return False
        print("入力が不正です。y / N で入力してください。")


def phone_to_imessage_formats(phone):
    """電話番号を Messages が受け付ける形式のリストに変換。複数形式を試す。"""
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return []
    forms = [phone]
    if digits.startswith("0") and len(digits) >= 10:
        e164 = "+81" + digits.lstrip("0")
        if e164 not in forms:
            forms.append(e164)
    elif digits.startswith("81") and len(digits) >= 11:
        e164 = "+" + digits
        if e164 not in forms:
            forms.append(e164)
    return forms


def send_imessage(phone, body_text, attachment_paths=None):
    """AppleScript で iMessage を送信。本文＋添付ファイル。成功で True。"""
    if attachment_paths is None:
        attachment_paths = []
    phone_esc = phone.replace("\\", "\\\\").replace('"', '\\"')
    parts = [p.replace("\\", "\\\\").replace('"', '\\"') for p in body_text.split("\n")]
    msg_expr = " & return & ".join(f'"{p}"' for p in parts)

    file_blocks = []
    for path in attachment_paths:
        posix_path = str(path.resolve())
        path_esc = posix_path.replace("\\", "\\\\").replace('"', '\\"')
        file_blocks.append(
            f'''        set theFile to POSIX file "{path_esc}"
        send theFile to targetBuddy
        delay 0.3'''
        )

    file_section = "\n".join(file_blocks) if file_blocks else ""

    script = f'''tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        set targetBuddy to buddy "{phone_esc}" of targetService
        set msg to {msg_expr}
        send msg to targetBuddy
        delay 0.5
{file_section}
    end tell'''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.returncode == 0


def find_partner(partners, name_or_folder):
    """name または folder でパートナーを検索。"""
    name_or_folder = (name_or_folder or "").strip()
    for p in partners:
        if p.get("name") == name_or_folder or p.get("folder") == name_or_folder:
            return p
    return None


def get_latest_message_from_partner(service, partner_emails):
    """パートナー宛の直近メールを1件取得。threadId, message_id, subject, message_id_header を返す。"""
    if not partner_emails:
        return None
    from_query = " OR ".join(f"from:{e}" for e in partner_emails)
    query = f"({from_query}) newer_than:90d"
    result = service.users().messages().list(userId="me", q=query, maxResults=1).execute()
    messages = result.get("messages", [])
    if not messages:
        return None

    msg = messages[0]
    full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
    headers = full.get("payload", {}).get("headers", [])

    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
    msg_id_header = None
    for h in headers:
        if h["name"].lower() == "message-id":
            msg_id_header = h["value"]
            break

    thread_id = full.get("threadId", "")
    return {
        "thread_id": thread_id,
        "message_id": msg["id"],
        "subject": subject,
        "message_id_header": msg_id_header or f"<{msg['id']}@mail.gmail.com>",
    }


ATTACHMENT_EXCLUDE_NAMES = {".gitkeep", ".DS_Store"}


def collect_attachment_files(attach_dir):
    """送信添付フォルダ内のファイルを列挙。.gitkeep / .DS_Store は送信対象から除外する。"""
    attach_dir.mkdir(parents=True, exist_ok=True)
    return [f for f in attach_dir.iterdir() if f.is_file() and f.name not in ATTACHMENT_EXCLUDE_NAMES]


def build_reply_message(to_email, subject, body_text, ref_info, attachment_paths):
    """返信用の MIME メッセージを構築。"""
    msg = MIMEMultipart()
    msg["To"] = to_email
    msg["Subject"] = subject

    if ref_info and ref_info.get("message_id_header"):
        msg["In-Reply-To"] = ref_info["message_id_header"]
        msg["References"] = ref_info["message_id_header"]

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

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return {"raw": raw}


def append_sent_to_yoritoori(folder_path, partner_name, subject, body, attachment_names):
    """やり取り.md に送信履歴を追記。"""
    md_path = base_path / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"{YORITOORI_FILENAME} が見つかりません: {md_path}", file=sys.stderr)
        return False

    date_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    summary = subject if (subject and subject != "（件名を記入）") else make_summary(body)
    subject_block = f"**件名**: {subject}\n" if subject else ""
    attach_block = ""
    if attachment_names:
        attach_block = "\n**添付ファイル**: " + ", ".join(attachment_names) + "\n"

    block = f"""

### {date_str}｜{partner_name}｜自分から送信｜{summary}

{subject_block}{body}{attach_block}

---
"""
    content = md_path.read_text(encoding="utf-8")
    marker = "## やり取り（時系列）"
    if marker in content:
        after_marker = content[content.find(marker) :]
        m = re.search(r"\n\n### [12]\d{3}/\d{2}/\d{2}", after_marker)
        if m:
            pos = content.find(marker) + m.start() + 2
            content = content[:pos] + block.strip() + "\n\n" + content[pos:]
        else:
            pos = content.find(marker) + len(marker)
            content = content[:pos].rstrip() + "\n\n" + block.strip() + "\n\n" + content[pos:].lstrip()
    else:
        content += block
    md_path.write_text(content, encoding="utf-8")
    return True


def move_attachments_to_past(attach_dir, attachment_paths):
    """送信添付フォルダ内のファイルを「送信添付(過去)」へ移動する。"""
    if not attachment_paths:
        return
    past_dir = resolve_past_attach_dir(attach_dir.parent)
    past_dir.mkdir(parents=True, exist_ok=True)
    for path in attachment_paths:
        if path.is_file():
            dest = past_dir / path.name
            if dest.exists():
                stem, suffix = path.stem, path.suffix
                for i in range(1, 100):
                    dest = past_dir / f"{stem}_{i}{suffix}"
                    if not dest.exists():
                        break
            shutil.move(str(path), str(dest))
            print(f"  添付を移動: {path.name} → {past_dir.name}/")


def run_imessage_flow(partner, folder_path, partner_name, draft_path, body_text, dry_run):
    """phones のみのパートナー向け iMessage 送信。送信添付フォルダ内のファイルも添付。"""
    phones = [p.strip() for p in partner.get("phones", []) if p.strip()]
    if not phones:
        print(f"エラー: {partner_name} に電話番号が登録されていません。", file=sys.stderr)
        sys.exit(1)

    phone = phones[0]
    formats = phone_to_imessage_formats(phone)

    attach_dir = resolve_attach_dir(base_path / folder_path)
    attachment_paths = collect_attachment_files(attach_dir)
    attachment_names = [p.name for p in attachment_paths]

    if dry_run:
        return

    append_sent_to_yoritoori(folder_path, partner_name, "（iMessage）", body_text, attachment_names)
    print("送信下書きの内容をやり取りに保存しました。")

    last_err = None
    for fmt in formats:
        if send_imessage(fmt, body_text, attachment_paths):
            print(f"iMessage 送信しました: {partner_name} ({phone})")
            if attachment_names:
                print(f"  添付: {', '.join(attachment_names)}")
            move_attachments_to_past(attach_dir, attachment_paths)
            return
        last_err = f"形式 {fmt} で送信失敗"
    print(f"エラー: iMessage 送信に失敗しました。{last_err}", file=sys.stderr)
    print("※やり取りには送信内容を追記済みです。送信のみ失敗しています。", file=sys.stderr)
    sys.exit(1)


def run_gmail_flow(partner, folder_path, partner_name, draft_path, subject, body_text, dry_run):
    """emails ありのパートナー向け Gmail 返信送信。"""
    emails = [e.lower().strip() for e in partner.get("emails", [])]
    if not credentials_path.exists():
        print("エラー: credentials.json が見つかりません", file=sys.stderr)
        sys.exit(1)

    use_subject = subject if subject and subject != "（件名を記入）" else None

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
        print("token.json を保存しました。")

    service = build("gmail", "v1", credentials=creds)

    ref_info = get_latest_message_from_partner(service, emails)
    if not ref_info:
        print(f"エラー: {partner_name} 宛の直近90日以内のメールが見つかりません。返信先を特定できません。", file=sys.stderr)
        sys.exit(1)

    if not use_subject:
        orig_subject = ref_info.get("subject", "")
        if orig_subject and not orig_subject.strip().upper().startswith("RE:"):
            use_subject = f"Re: {orig_subject}"
        else:
            use_subject = orig_subject or "Re:"
    if not use_subject:
        use_subject = "Re:"

    attach_dir = resolve_attach_dir(base_path / folder_path)
    attachment_paths = collect_attachment_files(attach_dir)
    attachment_names = [p.name for p in attachment_paths]

    to_email = emails[0]
    message_dict = build_reply_message(to_email, use_subject, body_text, ref_info, attachment_paths)
    send_body = {"raw": message_dict["raw"], "threadId": ref_info["thread_id"]}

    if dry_run:
        return

    append_sent_to_yoritoori(folder_path, partner_name, use_subject, body_text, attachment_names)
    print("送信下書きの内容をやり取りに保存しました。")

    try:
        service.users().messages().send(userId="me", body=send_body).execute()
        print(f"送信しました: {partner_name} ({to_email})")
        if attachment_names:
            print(f"  添付: {', '.join(attachment_names)}")
        move_attachments_to_past(attach_dir, attachment_paths)
    except Exception as e:
        print(f"送信エラー: {e}", file=sys.stderr)
        print("※やり取りには送信内容を追記済みです。送信のみ失敗しています。", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="送信下書きをパートナーに送信")
    parser.add_argument("--partner", required=True, help="パートナー名またはフォルダ名（例: 立木, ミニテック）")
    parser.add_argument("--via", choices=["auto", "gmail", "imessage"], default="auto")
    parser.add_argument("--skip-confirm", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-chrline",
        action="store_true",
        help="送信前の CHRLINE セッション確認・再ログインをしない（既定は実施）",
    )
    parser.add_argument("--move-attachments-only", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load(contact_path.read_text(encoding="utf-8"))
    partners = config.get("partners", [])

    partner = find_partner(partners, args.partner)
    if not partner:
        print(f"エラー: パートナー '{args.partner}' が見つかりません。", file=sys.stderr)
        sys.exit(1)

    emails = [e.lower().strip() for e in partner.get("emails", [])]
    phones = [p.strip() for p in partner.get("phones", []) if p.strip()]

    if not emails and not phones:
        print(f"エラー: {partner.get('name', args.partner)} にメールアドレスも電話番号も登録されていません。", file=sys.stderr)
        sys.exit(1)

    folder_path = partner["folder"]
    partner_name = partner["name"]
    draft_path = base_path / folder_path / DRAFT_FILENAME

    if args.move_attachments_only:
        attach_dir = resolve_attach_dir(base_path / folder_path)
        attachment_paths = collect_attachment_files(attach_dir)
        if not attachment_paths:
            print(f"送信添付フォルダにファイルがありません: {attach_dir}")
            return
        move_attachments_to_past(attach_dir, attachment_paths)
        print(f"送信添付(過去)へ {len(attachment_paths)} 件移動しました。")
        return

    if not draft_path.exists():
        print(f"エラー: {DRAFT_FILENAME} が見つかりません: {draft_path}", file=sys.stderr)
        sys.exit(1)

    if not trigger_editor_save_all():
        print(
            "エラー: Cursor/VS Code の「すべて保存」に失敗しました。下書きが古いまま送信されるのを防ぐため、送信を中止します。",
            file=sys.stderr,
        )
        sys.exit(1)
    print("送信下書きを保存しました。（Cursor/VS Code の「すべて保存」を実行）")

    subject, body_text = parse_draft(draft_path)
    if not body_text.strip():
        print("エラー: 送信下書きが空です。", file=sys.stderr)
        sys.exit(1)

    chosen_via = args.via
    if chosen_via == "auto" and emails and phones:
        if sys.stdin is None or not sys.stdin.isatty():
            print(
                f"エラー: {partner_name} はメール/電話の両方が登録されています。非対話環境のため自動選択できません。 --via gmail または --via imessage を指定してください。",
                file=sys.stderr,
            )
            sys.exit(1)
        while True:
            print(f"{partner_name} は送信手段を選べます。どちらで送りますか？")
            print("  1) Gmail（メール返信）")
            print("  2) iMessage")
            choice = input("選択 (1/2): ").strip()
            if choice == "1":
                chosen_via = "gmail"
                break
            if choice == "2":
                chosen_via = "imessage"
                break
            print("入力が不正です。1 または 2 を入力してください。")
    elif chosen_via == "auto":
        chosen_via = "gmail" if emails else "imessage"

    attach_dir = resolve_attach_dir(base_path / folder_path)
    attachment_paths = collect_attachment_files(attach_dir)
    attachment_names = [p.name for p in attachment_paths]

    via_label = "Gmail（メール返信）" if chosen_via == "gmail" else "iMessage"
    if not confirm_before_send(
        partner_name=partner_name,
        via=via_label,
        draft_path=draft_path,
        subject=subject if chosen_via == "gmail" else "（iMessage）",
        body_text=body_text,
        attachment_names=attachment_names,
        skip_confirm=args.skip_confirm,
        dry_run=args.dry_run,
    ):
        return

    if not args.skip_chrline:
        ensure_chrline_session_before_partner_send()

    if chosen_via == "gmail":
        run_gmail_flow(partner, folder_path, partner_name, draft_path, subject, body_text, args.dry_run)
        return
    run_imessage_flow(partner, folder_path, partner_name, draft_path, body_text, args.dry_run)


if __name__ == "__main__":
    main()

