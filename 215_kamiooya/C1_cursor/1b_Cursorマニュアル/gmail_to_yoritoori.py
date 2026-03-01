#!/usr/bin/env python3
"""
Gmail の未読メールを取得し、送信元メールアドレスで連絡先一覧と照合。
マッチした場合、該当フォルダの やり取り.md に「相手から返信」として追記する。
添付ファイルは該当フォルダ内の「添付」サブフォルダに保存する。

--include-sent 指定時は、送信トレイ（SENT）からパートナーあてのメールを取得し、
やり取り.md に「自分から送信」として追記する（受信と同様の仕様で送信履歴を残す）。

前提:
  - Gmail API 設定済み（credentials.json, token.json）
  - 連絡先一覧.yaml にメールアドレスを登録済み
  - pip install -r requirements_gmail.txt 済み

使い方:
  python gmail_to_yoritoori.py                    # 未読を処理→漏れ確認（既読で未登録も追加）
  python gmail_to_yoritoori.py --include-read    # 漏れのみ（既読で未登録を追加）
  python gmail_to_yoritoori.py --include-sent    # 送信トレイをやり取りに追記（漏れのみ追加）
  python gmail_to_yoritoori.py --add-at "2026-02-11 14:30"  # 指定時刻（日本時間）のメールを追加
"""

import argparse
import base64
import email.utils as email_utils
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# メール日付・表示・比較はすべて日本時間で統一（OSのタイムゾーンに依存しない）
JST = ZoneInfo("Asia/Tokyo")

import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 設定
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent.parent / "C2_ルーティン作業" / "26_パートナー社への相談"
CONTACT_YAML = BASE_DIR / "000_共通" / "連絡先一覧.yaml"
CREDENTIALS_PATH = SCRIPT_DIR / "credentials.json"
TOKEN_PATH = SCRIPT_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def load_env():
    env_path = SCRIPT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r'^\s*([^#=]+)\s*=\s*(.+?)\s*$', line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip().strip('"\'')
                if val:
                    os.environ[key] = val


load_env()

credentials_path = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", CREDENTIALS_PATH))
token_path = Path(os.environ.get("GMAIL_TOKEN_PATH", TOKEN_PATH))
contact_path = Path(os.environ.get("CONTACT_LIST_PATH", CONTACT_YAML))
base_path = Path(os.environ.get("YORITOORI_BASE_PATH", BASE_DIR))

from yoritoori_utils import YORITOORI_FILENAME, resolve_incoming_attach_dir


def extract_email(from_header):
    if not from_header:
        return None
    m = re.search(r"<([^>]+)>", from_header)
    if m:
        return m.group(1).strip().lower()
    return from_header.strip().lower()


def extract_emails_from_header(to_header):
    """To/Cc ヘッダー文字列からメールアドレスを列挙。<> 内またはカンマ区切り。"""
    if not to_header or not to_header.strip():
        return []
    emails = []
    for part in re.split(r",", to_header):
        part = part.strip()
        m = re.search(r"<([^>]+)>", part)
        if m:
            emails.append(m.group(1).strip().lower())
        elif re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", part):
            emails.append(part.lower())
    return emails


def parse_email_body(payload):
    """メール本文を取得。multipart のネスト構造も再帰的に探索。"""
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


def format_date(dt):
    """日本時間で表示。タイムゾーン付きの場合は JST に変換してからフォーマット（OSに依存しない）。"""
    if dt.tzinfo:
        dt = dt.astimezone(JST).replace(tzinfo=None)
    return dt.strftime("%Y/%m/%d %H:%M")


def collect_attachment_parts(payload):
    parts = []

    def walk(p):
        if not p:
            return
        if p.get("filename") and p.get("body", {}).get("attachmentId"):
            parts.append({"filename": p["filename"], "attachmentId": p["body"]["attachmentId"]})
        if p.get("parts"):
            for child in p["parts"]:
                walk(child)

    walk(payload)
    return parts


def collect_attachment_filenames(payload):
    """送信メールのペイロードから添付ファイル名のみを列挙（ダウンロードしない）。"""
    names = []

    def walk(p):
        if not p:
            return
        if p.get("filename"):
            names.append(p["filename"])
        if p.get("parts"):
            for child in p["parts"]:
                walk(child)

    walk(payload)
    return names


def sanitize_filename(name):
    s = re.sub(r'[<>:"/\\|?*]', "_", name)
    s = re.sub(r"\s+", "_", s)
    return s or "attachment"


def save_attachments(service, message_id, payload, folder_path, date_str):
    attachment_parts = collect_attachment_parts(payload)
    if not attachment_parts:
        return []

    attach_dir = resolve_incoming_attach_dir(base_path / folder_path)
    attach_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = date_str.replace("/", "").replace(" ", "_")
    saved = []

    for i, part in enumerate(attachment_parts):
        att = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=part["attachmentId"])
            .execute()
        )
        data = att.get("data", "")
        data = data.replace("-", "+").replace("_", "/")
        buf = base64.b64decode(data)

        safe = sanitize_filename(part["filename"])
        ext = os.path.splitext(safe)[1]
        base_name = os.path.splitext(safe)[0]

        if len(attachment_parts) > 1:
            dest_path = attach_dir / f"{date_prefix}_{base_name}_{i + 1}{ext}"
        else:
            dest_path = attach_dir / f"{date_prefix}_{safe}"

        counter = 0
        while dest_path.exists():
            counter += 1
            stem, ext = dest_path.stem, dest_path.suffix
            dest_path = attach_dir / f"{stem}_{counter}{ext}"

        dest_path.write_bytes(buf)
        saved.append(dest_path.name)

    return saved


def parse_yoritoori_existing():
    """各やり取り.md から既存エントリの (subject, date_yyyymmdd) を抽出。"""
    existing = set()
    for folder in base_path.iterdir():
        if not folder.is_dir():
            continue
        md_path = folder / YORITOORI_FILENAME
        if not md_path.exists():
            continue
        content = md_path.read_text(encoding="utf-8")
        blocks = re.split(r"\n---\s*\n", content)
        for block in blocks:
            m = re.search(r"### (\d{4}/\d{2}/\d{2})(?:\s+(\d{1,2}:\d{2}))?｜.*｜相手から返信", block)
            if not m:
                continue
            date_part = m.group(1)
            subject = ""
            sm = re.search(r"\*\*件名\*\*:\s*(.+)", block)
            if sm:
                subject = sm.group(1).strip()
            key = (subject, date_part.replace("/", "-"))
            existing.add(key)
    return existing


def parse_yoritoori_existing_sent():
    """各やり取り.md から既存の「自分から送信」エントリの (subject, date_yyyymmdd) を抽出。重複判定用。"""
    existing = set()
    for folder in base_path.iterdir():
        if not folder.is_dir():
            continue
        md_path = folder / YORITOORI_FILENAME
        if not md_path.exists():
            continue
        content = md_path.read_text(encoding="utf-8")
        blocks = re.split(r"\n---\s*\n", content)
        for block in blocks:
            m = re.search(r"### (\d{4}/\d{2}/\d{2})(?:\s+(\d{1,2}:\d{2}))?｜.*｜自分から送信", block)
            if not m:
                continue
            date_part = m.group(1).replace("/", "-")
            subject = ""
            sm = re.search(r"\*\*件名\*\*:\s*(.+)", block)
            if sm:
                subject = sm.group(1).strip()
            existing.add((subject, date_part))
    return existing


def append_sent_to_yoritoori(folder_path, partner_name, date_str, subject, body, attachment_names=None):
    """やり取り.md に「自分から送信」ブロックを追記。送信トレイから取り込んだ用。"""
    from yoritoori_utils import make_summary

    if attachment_names is None:
        attachment_names = []

    md_path = base_path / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"{YORITOORI_FILENAME} が見つかりません: {md_path}", file=sys.stderr)
        return False

    summary = make_summary(body)
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
        after_marker = content[content.find(marker):]
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


def append_to_yoritoori(folder_path, partner_name, date_str, body, attachment_names=None, subject=""):
    if attachment_names is None:
        attachment_names = []

    from yoritoori_utils import make_summary, YORITOORI_FILENAME, resolve_incoming_attach_dir

    md_path = base_path / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"{YORITOORI_FILENAME} が見つかりません: {md_path}", file=sys.stderr)
        return False

    summary = make_summary(body)
    subject_block = ""
    if subject:
        subject_block = f"**件名**: {subject}\n"

    attach_block = ""
    if attachment_names:
        attach_block = "\n**添付ファイル**: " + ", ".join(attachment_names) + "（添付フォルダに保存）\n"

    content = md_path.read_text(encoding="utf-8")
    block = f"""

### {date_str}｜{partner_name}｜相手から返信｜{summary}

{subject_block}{body}{attach_block}

---
"""
    # 新しいメッセージを上に表示（時系列で新しい順）
    marker = "## やり取り（時系列）"
    if marker in content:
        after_marker = content[content.find(marker):]
        # テンプレート(20XX)を飛ばし、最初の実エントリ(2026/02/11等)の直前に挿入
        m = re.search(r"\n\n### [12]\d{3}/\d{2}/\d{2}", after_marker)
        if m:
            pos = content.find(marker) + m.start() + 2  # +2 で \n\n の後
            content = content[:pos] + block.strip() + "\n\n" + content[pos:]
        else:
            pos = content.find(marker) + len(marker)
            content = content[:pos].rstrip() + "\n\n" + block.strip() + "\n\n" + content[pos:].lstrip()
    else:
        content += block
    md_path.write_text(content, encoding="utf-8")
    return True


def process_message(service, msg, email_to_partner, mark_read=True):
    """1件のメールを処理し、やり取りに追記。追記したら True。"""
    full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
    headers = full.get("payload", {}).get("headers", [])

    from_val = next((h["value"] for h in headers if h["name"].lower() == "from"), None)
    from_date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)
    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")

    email = extract_email(from_val)
    if not email:
        return False

    partner = email_to_partner.get(email)
    if not partner:
        return False

    payload = full.get("payload", {})
    body = parse_email_body(payload)

    if from_date:
        try:
            dt = email_utils.parsedate_to_datetime(from_date)
            date_str = format_date(dt)
        except (TypeError, ValueError):
            date_str = format_date(datetime.now())
    else:
        date_str = format_date(datetime.now())

    attachment_names = []
    try:
        attachment_names = save_attachments(
            service, msg["id"], payload, partner["folder"], date_str
        )
    except Exception as e:
        print(f"添付の保存中にエラー: {e}", file=sys.stderr)

    ok = append_to_yoritoori(
        partner["folder"], partner["name"], date_str, body, attachment_names, subject
    )
    if ok:
        log_msg = f"追記: {partner['name']} ({email}) - {subject[:40]}..."
        if attachment_names:
            log_msg += f" [添付{len(attachment_names)}件]"
        print(log_msg)
        if mark_read:
            service.users().messages().modify(
                userId="me",
                id=msg["id"],
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Gmail のメールをやり取り.md に追記")
    parser.add_argument("--include-read", action="store_true", help="既読含む。やり取りの漏れを検出して追加（受信のみ）")
    parser.add_argument("--include-sent", action="store_true", help="送信トレイをやり取りに追記（自分から送信の漏れを追加）")
    parser.add_argument("--add-at", metavar="DATETIME", help='指定時刻のメールを追加。例: "2026-02-11 14:30"')
    args = parser.parse_args()

    if not credentials_path.exists():
        print("エラー: credentials.json が見つかりません", file=sys.stderr)
        print(f"配置場所: {credentials_path}", file=sys.stderr)
        print("Gmail_API_設定手順.md を参照してください。", file=sys.stderr)
        sys.exit(1)

    config = yaml.safe_load(contact_path.read_text(encoding="utf-8"))
    partners = config.get("partners", [])

    email_to_partner = {}
    for p in partners:
        for e in p.get("emails", []):
            email_to_partner[e.lower().strip()] = p

    if not email_to_partner:
        print("警告: 連絡先一覧.yaml にメールアドレスが1件も登録されていません。", file=sys.stderr)
        print("emails に実際のアドレスを追加してください。", file=sys.stderr)
        sys.exit(1)

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
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print("token.json を保存しました。")
        sys.stdout.flush()

    service = build("gmail", "v1", credentials=creds)

    if args.add_at:
        _run_add_at(service, email_to_partner, args.add_at)
    elif args.include_read:
        _run_include_read(service, email_to_partner)
    elif args.include_sent:
        print("送信トレイを確認しています...")
        sys.stdout.flush()
        _run_include_sent(service, email_to_partner)
    else:
        # 通常: 未読を処理 → 受信の漏れ確認 → 送信トレイの漏れ確認
        print("未読メールを確認しています...")
        sys.stdout.flush()
        _run_unread_only(service, email_to_partner)
        print()
        print("漏れメールを確認しています...")
        sys.stdout.flush()
        _run_include_read(service, email_to_partner)
        print()
        print("送信トレイを確認しています...")
        sys.stdout.flush()
        _run_include_sent(service, email_to_partner)
    print("完了しました。")
    sys.stdout.flush()


def _run_unread_only(service, email_to_partner):
    """未読メールを処理し、やり取りに追記して既読にする。"""
    result = service.users().messages().list(userId="me", q="is:unread", maxResults=50).execute()
    messages = result.get("messages", [])

    if not messages:
        print("未読メールはありません。")
        sys.stdout.flush()
        return 0

    appended = 0
    for msg in messages:
        if process_message(service, msg, email_to_partner, mark_read=True):
            appended += 1

    if appended > 0:
        print(f"{appended} 件の返信をやり取りに追記し、既読にしました。")
    else:
        print("連絡先一覧に一致する未読メールはありませんでした。")
    sys.stdout.flush()
    return appended


def _run_include_read(service, email_to_partner):
    """既読含む。やり取りの漏れを検出して追加。"""
    existing = parse_yoritoori_existing()

    partner_emails = list(email_to_partner.keys())
    from_query = " OR ".join(f"from:{e}" for e in partner_emails)
    query = f"({from_query}) newer_than:30d"
    result = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
    messages = result.get("messages", [])

    if not messages:
        print("直近30日にパートナーからのメールはありませんでした。")
        sys.stdout.flush()
        return 0

    appended = 0
    for msg in messages:
        full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
        headers = full.get("payload", {}).get("headers", [])
        from_val = next((h["value"] for h in headers if h["name"].lower() == "from"), None)
        from_date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")

        email = extract_email(from_val)
        partner = email_to_partner.get(email) if email else None
        if not partner:
            continue

        if from_date:
            try:
                dt = email_utils.parsedate_to_datetime(from_date)
                date_str = format_date(dt)
            except (TypeError, ValueError):
                date_str = format_date(datetime.now())
        else:
            date_str = format_date(datetime.now())

        date_key = date_str[:10].replace("/", "-")
        key = (subject.strip(), date_key)
        if key in existing:
            continue

        if process_message(service, msg, email_to_partner, mark_read=False):
            appended += 1
            existing.add(key)

    if appended > 0:
        print(f"{appended} 件の漏れメールをやり取りに追記しました。")
    else:
        print("やり取りに漏れているメールはありませんでした。")
    sys.stdout.flush()
    return appended


def _run_include_sent(service, email_to_partner):
    """送信トレイ（SENT）からパートナーあてのメールを取得し、やり取りに「自分から送信」として追記。"""
    existing_sent = parse_yoritoori_existing_sent()
    partner_emails = list(email_to_partner.keys())
    to_query = " OR ".join(f"to:{e}" for e in partner_emails)
    query = f"in:sent ({to_query}) newer_than:30d"
    result = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
    messages = result.get("messages", [])

    if not messages:
        print("直近30日にパートナーあての送信メールはありませんでした。")
        sys.stdout.flush()
        return 0

    appended = 0
    for msg in messages:
        full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
        headers = full.get("payload", {}).get("headers", [])
        to_val = next((h["value"] for h in headers if h["name"].lower() == "to"), None)
        from_date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")

        to_emails = extract_emails_from_header(to_val)
        partner = None
        for e in to_emails:
            if e in email_to_partner:
                partner = email_to_partner[e]
                break
        if not partner:
            continue

        payload = full.get("payload", {})
        body = parse_email_body(payload)
        attachment_names = collect_attachment_filenames(payload)

        if from_date:
            try:
                dt = email_utils.parsedate_to_datetime(from_date)
                date_str = format_date(dt)
            except (TypeError, ValueError):
                date_str = format_date(datetime.now())
        else:
            date_str = format_date(datetime.now())

        date_key = date_str[:10].replace("/", "-")
        key = (subject.strip(), date_key)
        if key in existing_sent:
            continue

        if append_sent_to_yoritoori(
            partner["folder"], partner["name"], date_str, subject.strip(), body, attachment_names
        ):
            appended += 1
            existing_sent.add(key)
            print(f"追記（送信）: {partner['name']} - {subject[:50]}...")

    if appended > 0:
        print(f"{appended} 件の送信メールをやり取りに追記しました。")
    else:
        print("やり取りに漏れている送信メールはありませんでした。")
    sys.stdout.flush()
    return appended


def _run_add_at(service, email_to_partner, add_at_str):
    """指定時刻（日本時間）±30分 のメールを追加。日付・比較はすべて JST で行う。"""
    try:
        target_dt = datetime.strptime(add_at_str.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            target_dt = datetime.strptime(add_at_str.strip(), "%H:%M")
            now = datetime.now()
            target_dt = target_dt.replace(year=now.year, month=now.month, day=now.day)
        except ValueError:
            print(f"エラー: 時刻形式が不正です。YYYY-MM-DD HH:MM または HH:MM を指定してください: {add_at_str}", file=sys.stderr)
            sys.exit(1)

    start_dt = target_dt - timedelta(minutes=30)
    end_dt = target_dt + timedelta(minutes=30)

    # 指定時刻は日本時間として解釈。Gmail の after/before は PST 等で解釈されるため、前後1日広めに取得してから日本時間でフィルタする
    partner_emails = list(email_to_partner.keys())
    from_query = " OR ".join(f"from:{e}" for e in partner_emails)
    after_date = (target_dt - timedelta(days=1)).strftime("%Y/%m/%d")
    before_date = (target_dt + timedelta(days=2)).strftime("%Y/%m/%d")
    query = f"({from_query}) after:{after_date} before:{before_date}"
    result = service.users().messages().list(userId="me", q=query, maxResults=50).execute()
    messages = result.get("messages", [])
    existing = parse_yoritoori_existing()
    appended = 0

    for msg in messages:
        full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
        headers = full.get("payload", {}).get("headers", [])
        from_date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
        if from_date:
            try:
                dt = email_utils.parsedate_to_datetime(from_date)
                if dt.tzinfo:
                    dt = dt.astimezone(JST).replace(tzinfo=None)
            except (TypeError, ValueError):
                dt = datetime.now(JST).replace(tzinfo=None)
        else:
            dt = datetime.now(JST).replace(tzinfo=None)

        # 比較は日本時間の時刻で（target_dt は「日本時間」として指定された時刻）
        if not (start_dt <= dt <= end_dt):
            continue

        date_str = format_date(dt)
        date_key = date_str[:10].replace("/", "-")
        if (subject.strip(), date_key) in existing:
            continue

        if process_message(service, msg, email_to_partner, mark_read=False):
            appended += 1
            existing.add((subject.strip(), date_key))

    if appended > 0:
        print(f"\n{appended} 件のメールをやり取りに追記しました。")
    else:
        print(f"{add_at_str} 前後30分に該当するメールは見つかりませんでした。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
