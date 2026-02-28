#!/usr/bin/env python3
"""
いけともAIニュース（from:ikeda@workstyle-evolution.co.jp、件名「注目AIニュース」）を
Gmail から取得し、指定フォルダ（いけともAIニュース）に保存する。

保存ルール:
  - 日付フォルダ（YYYYMMDD）内には画像のみを保存する。
  - MD ファイルは「いけともAIニュース」直下に置く。ファイル名は「注目AIニュース_YYYYMMDD.md」（西暦）。

前提:
  - Gmail API 設定済み（credentials.json, token.json）
  - pip install -r requirements_gmail.txt 済み
  - credentials は 215 フォルダの gmail_to_yoritoori と共通（環境変数で上書き可能）

使い方:
  python gmail_ai_news_save.py                    # デフォルト保存先へ保存（直近7日・未処理のみ）
  python gmail_ai_news_save.py --output /path     # 保存先を指定
  python gmail_ai_news_save.py --date 2026-02-06 # 指定日のメールのみ取得（試し保存向け）
  python gmail_ai_news_save.py --date 2026-02-06 --force  # 指定日を処理済みでも再保存
  環境変数 AI_NEWS_SAVE_PATH でも保存先を指定可能
"""

import argparse
import base64
import email.utils as email_utils
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 設定
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SAVE_PATH = Path(
    "/Users/matsunomasaharu/Library/CloudStorage/GoogleDrive-m19m.hrts83@gmail.com"
    "/マイドライブ/DX互助会_共有フォルダ/05_knowledge/いけともAIニュース"
)
# credentials は 215 フォルダの gmail_to_yoritoori と共通
DEFAULT_CREDENTIALS_DIR = Path(
    "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル"
)
CREDENTIALS_PATH = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", str(DEFAULT_CREDENTIALS_DIR / "credentials.json")))
TOKEN_PATH = Path(os.environ.get("GMAIL_TOKEN_PATH", str(DEFAULT_CREDENTIALS_DIR / "token.json")))

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

AI_NEWS_FROM = "ikeda@workstyle-evolution.co.jp"
AI_NEWS_SUBJECT = "注目AIニュース"


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

credentials_path = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", str(CREDENTIALS_PATH)))
token_path = Path(os.environ.get("GMAIL_TOKEN_PATH", str(TOKEN_PATH)))
save_path = Path(os.environ.get("AI_NEWS_SAVE_PATH", DEFAULT_SAVE_PATH))


def get_html_body(payload):
    """メール本文の HTML を取得。無ければ空文字。"""
    html = ""

    def walk(p):
        nonlocal html
        if not p:
            return
        if p.get("mimeType") == "text/html" and p.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8", errors="replace")
            return
        for child in p.get("parts") or []:
            if html:
                return
            walk(child)

    if payload.get("body") and payload["body"].get("data"):
        ct = (payload.get("mimeType") or "").lower()
        if "html" in ct:
            html = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    if not html and payload.get("parts"):
        walk(payload)
    return html


def parse_email_body(payload):
    """メール本文をテキストとして抽出。"""
    text = ""
    if payload.get("body") and payload["body"].get("data"):
        text = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
    if payload.get("parts"):
        for p in payload["parts"]:
            if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
                text = base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8")
                break
            if p.get("mimeType") == "text/html" and p.get("body", {}).get("data") and not text:
                html = base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8")
                text = re.sub(r"<[^>]+>", "\n", html)
                text = re.sub(r"\n+", "\n", text).strip()
    return text.strip()


# data URL 画像用の正規表現（img タグの src="data:image/...;base64,..." を抽出）
_DATA_URL_PATTERN = re.compile(
    r'<img[^>]+src=["\'](data:image/(png|jpeg|jpg|gif|webp);base64,[^"\']+)["\'][^>]*>',
    re.IGNORECASE | re.DOTALL,
)
# 外部 URL 画像用（img タグの src="https://..." を抽出）
_HTTPS_IMG_PATTERN = re.compile(
    r'<img[^>]+src=["\'](https://[^"\']+\.(?:png|jpe?g|gif|webp)(?:\?[^"\']*)?)["\'][^>]*>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_style_and_script(html):
    """<style>...</style> と <script>...</script> を除去して本文だけにする。"""
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "\n", html, flags=re.IGNORECASE)
    return html


def _compact_layout(text):
    """行間を詰め、レイアウトを整理する。"""
    lines = [line.strip() for line in text.splitlines()]
    out = []
    prev_blank = False
    for line in lines:
        # 空白・不可視文字のみの行は空行扱い
        cleaned = line.replace("\u200b", "").replace("\u00ad", "").replace("\u00a0", " ").strip()
        if not cleaned or re.match(r"^[\s\u00ad\u200b\u200c\u200d\ufeff\-­]+$", cleaned):
            if not prev_blank:
                out.append("")
            prev_blank = True
            continue
        # 残ったHTMLタグ風の行はスキップ
        if cleaned.startswith("<") and ">" in cleaned:
            continue
        if cleaned.startswith("<"):
            continue
        out.append(line)
        prev_blank = False
    result = "\n".join(out).strip()
    return re.sub(r"\n{3,}", "\n\n", result)


def _sanitize_folder_name(title, max_len=28):
    """フォルダ名用にタイトルを短く・安全な文字列にする。"""
    s = re.sub(r'[\\/:*?"<>|]', "_", title)
    s = s.strip().strip(".")[:max_len]
    return s or "未分類"


def _body_content_only(body):
    """本文の先頭ノイズを除き、中身（池田さん挨拶または ** 1. ～）から始める。"""
    for marker in ("Workstyle Evolutionの池田です", "** 1.", "1.オープンソースのAIエージェント"):
        idx = body.find(marker)
        if idx >= 0:
            return body[idx:].strip()
    return body


def _download_image(url, timeout=15):
    """URL から画像を取得。失敗時は None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AI-News-Save/1.0)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


# 17選のセクション見出し（HTML内の "1.タイトル" ～ "17.タイトル"、タグ直後または行頭）
_SECTION_HEADER_PATTERN = re.compile(
    r"(?:^|>)\s*(\d{1,2})\.\s*([^<\n]{2,}?)(?=<|\n)",
)


def extract_inline_images_from_html(html, date_dir, date_yyyymmdd, start_index=1):
    """
    HTML 内の画像を 17選のセクション別フォルダに保存し、短いファイル名で Markdown 参照を返す。
    戻り値: (置換済み本文・行間整理済み, 保存した相対パスのリスト)
    """
    if not html or not date_dir:
        return "", []

    html = _strip_style_and_script(html)
    date_dir = Path(date_dir)
    date_dir.mkdir(parents=True, exist_ok=True)

    # セクション見出しを位置順に取得（1.～17.）(start, end, num, title, folder_name)
    sections = []
    for m in _SECTION_HEADER_PATTERN.finditer(html):
        num = int(m.group(1))
        if 1 <= num <= 17:
            title = m.group(2).strip()
            folder_name = f"{num:02d}_{_sanitize_folder_name(title)}"
            sections.append((m.start(), m.end(), num, title, folder_name))

    # 画像タグを位置順に取得（data URL と https）
    img_entries = []  # (start, end, 'data'|'https', match)
    for m in _DATA_URL_PATTERN.finditer(html):
        img_entries.append((m.start(), m.end(), "data", m))
    for m in _HTTPS_IMG_PATTERN.finditer(html):
        img_entries.append((m.start(), m.end(), "https", m))
    img_entries.sort(key=lambda x: x[0])

    section_folders = {0: "00_イントロ"}
    for _, _, num, _, folder_name in sections:
        section_folders[num] = folder_name
    section_counters = {}  # section_num -> 図解N の N

    # 位置でソートした「区切り」リスト（セクション or 画像）を作り、順に処理
    events = [(s[0], "section", s) for s in sections] + [(e[0], "img", e) for e in img_entries]
    events.sort(key=lambda x: x[0])

    output_parts = []
    current_section = 0
    pos = 0

    for event_pos, kind, data in events:
        # 直前のテキストを追加（タグ除去してテキスト化）
        segment = html[pos:event_pos]
        segment = re.sub(r"<br\s*/?>", "\n", segment, flags=re.IGNORECASE)
        segment = re.sub(r"</p>", "\n", segment, flags=re.IGNORECASE)
        segment = re.sub(r"<[^>]+>", "\n", segment)
        segment = re.sub(r"\n+", "\n", segment).strip()
        if segment:
            output_parts.append(segment)

        if kind == "section":
            _, end_pos, num, title, _ = data
            output_parts.append(f"** {num}. {title} **")
            current_section = num
            pos = end_pos
            continue

        # kind == "img"
        _, _, src_kind, match = data
        # イントロ（00_イントロ）の図解は保存・表示しない
        if current_section == 0:
            pos = match.end()
            continue

        folder_name = section_folders.get(current_section, "00_イントロ")
        section_dir = date_dir / folder_name
        section_dir.mkdir(parents=True, exist_ok=True)
        n = section_counters.get(current_section, 0) + 1
        section_counters[current_section] = n

        if src_kind == "data":
            data_url = match.group(1)
            subtype = (match.group(2) or "png").lower()
            ext = ".png" if subtype == "png" else ".jpg" if subtype in ("jpeg", "jpg") else f".{subtype}"
            head, _, b64 = data_url.partition(";base64,")
            raw = base64.b64decode(b64) if b64 else None
        else:
            url = match.group(1)
            ext = Path(url.split("?")[0]).suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                ext = ".png"
            raw = _download_image(match.group(1))

        if not raw:
            pos = match.end()
            continue

        fname = f"図解{n}{ext}"
        dest = section_dir / fname
        cnt = 0
        while dest.exists():
            cnt += 1
            dest = section_dir / f"図解{n}_{cnt}{ext}"
            fname = dest.name
        dest.write_bytes(raw)
        # MD はいけともAIニュース直下に置くため、画像は日付フォルダからの相対パス
        rel_path = f"{date_yyyymmdd}/{folder_name}/{fname}"
        output_parts.append(f"![図解]({rel_path})")
        pos = match.end()

    # 残り
    segment = html[pos:]
    segment = re.sub(r"<br\s*/?>", "\n", segment, flags=re.IGNORECASE)
    segment = re.sub(r"</p>", "\n", segment, flags=re.IGNORECASE)
    segment = re.sub(r"<[^>]+>", "\n", segment)
    segment = re.sub(r"\n+", "\n", segment).strip()
    if segment:
        output_parts.append(segment)

    body = "\n\n".join(output_parts)
    body = _compact_layout(body)
    body = _body_content_only(body)
    saved_count = sum(section_counters.values())
    return body, saved_count


def get_sunday_of_week(dt):
    """指定日が含まれる週の日曜日を返す。"""
    days_back = (dt.weekday() + 1) % 7  # Mon=0→1, Tue=1→2, ..., Sun=6→0
    return dt - timedelta(days=days_back)


def collect_all_attachment_parts(payload):
    """添付・インライン画像を含む、attachmentId を持つ全パートを収集。"""
    parts = []

    def walk(p):
        if not p:
            return
        body = p.get("body", {})
        if body.get("attachmentId"):
            filename = p.get("filename") or ""
            content_id = ""
            for h in p.get("headers", []):
                if h.get("name", "").lower() == "content-id":
                    content_id = (h.get("value") or "").strip("<>")
                    break
            mime_type = p.get("mimeType", "application/octet-stream")
            parts.append({
                "filename": filename,
                "attachmentId": body["attachmentId"],
                "contentId": content_id,
                "mimeType": mime_type,
            })
        if p.get("parts"):
            for child in p["parts"]:
                walk(child)

    walk(payload)
    return parts


def ext_from_mime(mime_type):
    """MIME タイプから拡張子を推定。"""
    m = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    return m.get(mime_type.lower(), ".png")


def save_attachments(service, message_id, payload, base_dir, date_yyyymmdd):
    """添付・インライン画像を base_dir 直下に保存。戻り値は (ファイル名リスト, 本文中参照用のマークダウン行リスト)。"""
    all_parts = collect_all_attachment_parts(payload)
    if not all_parts:
        return [], []

    base_dir.mkdir(parents=True, exist_ok=True)
    saved_names = []
    md_refs = []

    for i, part in enumerate(all_parts):
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

        ext = ext_from_mime(part["mimeType"])
        fname = f"添付{i + 1}{ext}"
        dest = base_dir / fname

        counter = 0
        while dest.exists():
            counter += 1
            dest = base_dir / f"添付{i + 1}_{counter}{ext}"
            fname = dest.name

        dest.write_bytes(buf)
        saved_names.append(fname)
        # MD はいけともAIニュース直下に置くため、画像は日付フォルダ付きの相対パス
        md_refs.append(f"![添付{i + 1}]({date_yyyymmdd}/{fname})")

    return saved_names, md_refs


PROCESSED_IDS_FILE = ".ai_news_processed.json"


def load_processed_ids(base_dir):
    """処理済みメールIDのセットを読み込む。"""
    path = base_dir / PROCESSED_IDS_FILE
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("processed_ids", []))
    except Exception:
        return set()


def save_processed_id(base_dir, msg_id):
    """処理済みメールIDを追記する。"""
    path = base_dir / PROCESSED_IDS_FILE
    processed = load_processed_ids(base_dir)
    processed.add(msg_id)
    path.write_text(json.dumps({"processed_ids": list(processed)}, ensure_ascii=False, indent=0), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="いけともAIニュースを保存")
    parser.add_argument("--output", "-o", metavar="DIR", help="保存先フォルダ")
    parser.add_argument("--dry-run", action="store_true", help="保存せずに確認のみ")
    parser.add_argument("--date", metavar="YYYY-MM-DD", help="指定日のメールのみ取得（例: 2026-02-06）")
    parser.add_argument("--force", action="store_true", help="処理済みメールも再保存する（--date と併用で試し保存向け）")
    parser.add_argument("--list", action="store_true", help="送信者からの直近メール一覧を表示（件名・日付）。アカウント確認用")
    parser.add_argument("--allow-forwarded", action="store_true", help="転送メールも対象にする（件名に「注目AIニュース」を含むメールを差出人不問で検索）")
    args = parser.parse_args()

    out_dir = Path(args.output) if args.output else save_path
    if args.dry_run:
        print(f"[dry-run] 保存先: {out_dir}")
        print(f"[dry-run] 検索: from:{AI_NEWS_FROM} subject:\"{AI_NEWS_SUBJECT}\" newer_than:7d")

    if not credentials_path.exists():
        print("エラー: credentials.json が見つかりません", file=sys.stderr)
        print(f"配置場所: {credentials_path}", file=sys.stderr)
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

    service = build("gmail", "v1", credentials=creds)

    if args.list:
        list_query = f"from:{AI_NEWS_FROM} newer_than:30d"
        list_result = service.users().messages().list(userId="me", q=list_query, maxResults=20).execute()
        list_msgs = list_result.get("messages", [])
        if not list_msgs:
            print(f"直近30日間に {AI_NEWS_FROM} からのメールはありませんでした。")
            return 0
        print(f"直近30日間の {AI_NEWS_FROM} からのメール（最大20件）:\n")
        for m in list_msgs:
            full = service.users().messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=["Subject", "Date"]).execute()
            headers = full.get("payload", {}).get("headers", [])
            subj = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
            date_h = next((h["value"] for h in headers if h["name"].lower() == "date"), "")
            print(f"  Date: {date_h}")
            print(f"  Subject: {subj}")
            print(f"  Id: {m['id']}\n")
        return 0

    if args.date:
        try:
            day = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print("エラー: --date は YYYY-MM-DD 形式で指定してください。", file=sys.stderr)
            sys.exit(1)
        # タイムゾーンずれを考慮し、前日〜翌日で検索
        day_before = day - timedelta(days=1)
        day_after = day + timedelta(days=2)
        after_str = f"{day_before.year}/{day_before.month}/{day_before.day}"
        before_str = f"{day_after.year}/{day_after.month}/{day_after.day}"
        if args.allow_forwarded:
            query = f'subject:"{AI_NEWS_SUBJECT}" after:{after_str} before:{before_str}'
        else:
            query = f'from:{AI_NEWS_FROM} subject:"{AI_NEWS_SUBJECT}" after:{after_str} before:{before_str}'
    else:
        if args.allow_forwarded:
            query = f'subject:"{AI_NEWS_SUBJECT}" newer_than:7d'
        else:
            query = f'from:{AI_NEWS_FROM} subject:"{AI_NEWS_SUBJECT}" newer_than:7d'

    result = service.users().messages().list(userId="me", q=query, maxResults=20).execute()
    messages = result.get("messages", [])

    if not messages:
        print("該当メールはありませんでした。" + (f"（指定日: {args.date}）" if args.date else "（直近7日間）"))
        return 0

    # 処理済みIDは save_path 直下で管理（日付フォルダではなく）
    processed_ids = load_processed_ids(save_path) if not args.force else set()
    saved_count = 0

    for msg in messages:
        if msg["id"] in processed_ids:
            continue

        full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
        headers = full.get("payload", {}).get("headers", [])
        from_date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")

        if from_date:
            try:
                dt = email_utils.parsedate_to_datetime(from_date)
            except (TypeError, ValueError):
                dt = datetime.now()
        else:
            dt = datetime.now()

        if args.date and dt.date() != day:
            continue

        sunday = get_sunday_of_week(dt)
        date_yyyymmdd = sunday.strftime("%Y%m%d")
        # 保存先は日付フォルダ（05_knowledge/いけともAIニュース/20260201/）
        date_dir = save_path / date_yyyymmdd

        payload = full.get("payload", {})

        if args.dry_run:
            print(f"[dry-run] 保存予定: 注目AIニュース_{date_yyyymmdd}.md（いけともAIニュース直下）, 画像: {date_yyyymmdd}/ ({subject[:40]}...)")
            continue

        date_dir.mkdir(parents=True, exist_ok=True)
        saved_names, md_refs = save_attachments(
            service, msg["id"], payload, date_dir, date_yyyymmdd
        )

        html = get_html_body(payload)
        inline_body = ""
        inline_img_count = 0
        if html:
            inline_body, inline_img_count = extract_inline_images_from_html(
                html, date_dir, date_yyyymmdd, start_index=1
            )
        body_text = inline_body if inline_body else parse_email_body(payload)

        # MD は「いけともAIニュース」直下に「注目AIニュース_YYYYMMDD.md」
        md_path = save_path / f"注目AIニュース_{date_yyyymmdd}.md"
        if md_path.exists():
            cnt = 2
            md_path = save_path / f"注目AIニュース_{date_yyyymmdd}_{cnt}.md"
            while md_path.exists():
                cnt += 1
                md_path = save_path / f"注目AIニュース_{date_yyyymmdd}_{cnt}.md"

        date_str = dt.strftime("%Y/%m/%d %H:%M")
        md_content = f"""# {subject}

**送信日時**: {date_str}

---

{body_text}
"""
        if md_refs:
            md_content += "\n\n---\n\n## 添付画像\n\n" + "\n\n".join(md_refs) + "\n"

        md_path.write_text(md_content, encoding="utf-8")
        save_processed_id(save_path, msg["id"])
        saved_count += 1
        total_imgs = len(saved_names) + inline_img_count
        print(f"保存: {md_path.name}（いけともAIニュース直下）, 画像: {date_yyyymmdd}/" + (f" [画像{total_imgs}件]" if total_imgs else ""))

        service.users().messages().modify(
            userId="me",
            id=msg["id"],
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()

        # 保存した集フォルダで画像テキスト索引を生成（Tesseract 等があれば）
        if not args.dry_run:
            index_script = SCRIPT_DIR / "build_image_index.py"
            if index_script.exists():
                try:
                    r = subprocess.run(
                        [sys.executable, str(index_script), date_yyyymmdd, "--base", str(save_path)],
                        cwd=str(save_path),
                        capture_output=True,
                        text=True,
                        timeout=600,
                    )
                    if r.returncode == 0:
                        print(f"索引: {date_yyyymmdd}/画像テキスト索引.md")
                    elif r.stderr and "Tesseract" in r.stderr:
                        print("(画像索引はスキップ: Tesseract 未導入)", flush=True)
                except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                    pass  # 索引失敗しても保存は成功のまま

    if saved_count > 0:
        print(f"\n{saved_count} 件のAIニュースを保存しました。")
    elif not args.dry_run:
        print("保存する未処理のメールはありませんでした。")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
