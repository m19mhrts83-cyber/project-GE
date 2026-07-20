#!/usr/bin/env python3
"""
Mac の iMessage/SMS（chat.db）から受信メッセージを取得し、
連絡先一覧の phones と照合して該当フォルダの やり取り.md に追記する。

添付は message_attachment_join 経由で取得し、
1.受信添付(Stock)/YYYY-MM-DD/ へコピー（Gmail / Chatwork と同様）。

前提:
  - Mac で iMessage が有効で、iPhone と同期されていること
  - フルディスクアクセスを Terminal/Cursor に付与済み
  - 連絡先一覧.yaml の phones に電話番号を登録済み
  - pip install -r requirements_gmail.txt 済み（PyYAML 使用）

使い方:
  python imessage_to_yoritoori.py
  python imessage_to_yoritoori.py --backfill-attachments
  python imessage_to_yoritoori.py --backfill-attachments --partner LEAF
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import yaml

# 設定
SCRIPT_DIR = Path(__file__).resolve().parent
from yoritoori_utils import (  # noqa: E402
    YORITOORI_FILENAME,
    default_yoritoori_base_dir,
    make_summary,
    mirror_yoritoori_md_to_gitrepos,
    parse_received_date_folder,
    resolve_incoming_attach_date_dir,
)

BASE_DIR = default_yoritoori_base_dir()
CONTACT_YAML = BASE_DIR / "000_共通" / "連絡先一覧.yaml"
CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"
PROCESSED_JSON = Path.home() / ".cursor" / "imessage_processed.json"

# Apple date epoch: 2001-01-01 00:00:00 UTC
APPLE_EPOCH = 978307200


def normalize_phone(phone):
    """電話番号を数字のみに正規化。09012345678 と +819012345678 を統一。"""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("81") and len(digits) > 10:
        return digits  # +81...
    if digits.startswith("0") and len(digits) == 10 or len(digits) == 11:
        return "81" + digits.lstrip("0")  # 090... -> 8190...
    return digits


def format_date_from_apple_ns(ns):
    """Apple の日付（ナノ秒、2001-01-01 からの経過）を YYYY/MM/DD HH:MM に変換。"""
    if ns is None:
        return datetime.now().strftime("%Y/%m/%d %H:%M")
    try:
        sec = int(ns) / 1_000_000_000 + APPLE_EPOCH
        dt = datetime.fromtimestamp(sec)
        return dt.strftime("%Y/%m/%d %H:%M")
    except (ValueError, OSError):
        return datetime.now().strftime("%Y/%m/%d %H:%M")


def load_processed():
    """処理済みメッセージ ROWID の最大値を取得。"""
    if not PROCESSED_JSON.exists():
        return 0
    try:
        data = json.loads(PROCESSED_JSON.read_text(encoding="utf-8"))
        return data.get("max_rowid", 0)
    except (json.JSONDecodeError, OSError):
        return 0


def save_processed(max_rowid):
    """処理済みの最大 ROWID を保存。"""
    PROCESSED_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_JSON.write_text(
        json.dumps({"max_rowid": max_rowid}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def try_parse_attributed_body(blob):
    """attributedBody からテキストを抽出を試す。失敗時は None。"""
    if not blob:
        return None
    try:
        # NSAttributedString のバイナリから NSString 部分を簡易抽出
        if isinstance(blob, bytes):
            text = blob.decode("utf-8", errors="ignore")
        else:
            text = str(blob)
        m = re.search(r'NSString[^"]*"([^"]*)"', text)
        if m:
            return m.group(1).strip()
        ascii_match = re.findall(r"[\x20-\x7e]{4,}", text)
        if ascii_match:
            return " ".join(ascii_match[:5]).strip()
    except Exception:
        pass
    return None


def sanitize_filename(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", name or "")
    s = re.sub(r"\s+", "_", s.strip())
    return s or "attachment"


def ensure_incoming_stock_dir(partner_folder: Path) -> Path:
    """1.受信添付(Stock) を用意（未作成時に「添付」へ落ちないようにする）。"""
    partner_folder = Path(partner_folder)
    stock = partner_folder / "1.受信添付(Stock)"
    if not stock.exists():
        alt = partner_folder / "添付"
        if not (alt.exists() and alt.is_dir()):
            stock.mkdir(parents=True, exist_ok=True)
    return stock


def fetch_attachments_for_message(conn, message_rowid: int) -> list[tuple[Path, str]]:
    """
    message_id に紐づく添付を返す。
    戻り値: [(src_path, display_name), ...]（ファイルが存在するもののみ）
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT a.filename, a.transfer_name, a.mime_type, a.is_sticker
            FROM attachment a
            JOIN message_attachment_join maj ON maj.attachment_id = a.ROWID
            WHERE maj.message_id = ?
            """,
            (message_rowid,),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        # 古いスキーマ等
        try:
            cur.execute(
                """
                SELECT a.filename, a.transfer_name, a.mime_type, 0
                FROM attachment a
                JOIN message_attachment_join maj ON maj.attachment_id = a.ROWID
                WHERE maj.message_id = ?
                """,
                (message_rowid,),
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError as e:
            print(f"  添付クエリ失敗 message_id={message_rowid}: {e}", file=sys.stderr)
            return []

    out: list[tuple[Path, str]] = []
    for filename, transfer_name, _mime, is_sticker in rows:
        if is_sticker:
            continue
        raw_path = (filename or "").strip()
        if not raw_path:
            continue
        src = Path(os.path.expanduser(raw_path))
        if not src.is_file():
            print(f"  添付ファイル不在: {src}", file=sys.stderr)
            continue
        display = (transfer_name or src.name or "attachment").strip()
        out.append((src, display))
    return out


def save_imessage_attachments(
    folder_path: str, date_str: str, items: list[tuple[Path, str]]
) -> list[str]:
    """
    iMessage 添付を 1.受信添付(Stock)/YYYY-MM-DD/ にコピー。
    戻り値: MD 用相対パス ["YYYY-MM-DD/保存名", ...]
    """
    if not items:
        return []

    partner_dir = BASE_DIR / folder_path
    ensure_incoming_stock_dir(partner_dir)
    attach_dir = resolve_incoming_attach_date_dir(partner_dir, date_str)
    date_folder = parse_received_date_folder(date_str)
    date_prefix = date_str.replace("/", "").replace(" ", "_")

    saved: list[str] = []
    for i, (src, display_name) in enumerate(items):
        safe = sanitize_filename(display_name or src.name)
        ext = os.path.splitext(safe)[1] or src.suffix
        base_name = os.path.splitext(safe)[0]
        if len(items) > 1:
            dest_path = attach_dir / f"{date_prefix}_{base_name}_{i + 1}{ext}"
        else:
            dest_path = attach_dir / f"{date_prefix}_{safe}"

        try:
            src_size = src.stat().st_size
        except OSError:
            print(f"  添付読取失敗: {src}", file=sys.stderr)
            continue

        counter = 0
        while dest_path.exists():
            try:
                if dest_path.stat().st_size == src_size:
                    break
            except OSError:
                pass
            counter += 1
            dest_path = attach_dir / f"{dest_path.stem}_{counter}{dest_path.suffix}"

        if not dest_path.exists() or dest_path.stat().st_size != src_size:
            shutil.copy2(src, dest_path)

        rel = f"{date_folder}/{dest_path.name}"
        saved.append(rel)
        print(f"  添付保存: {folder_path}/1.受信添付(Stock)/{rel}")

    return saved


def _attach_block(attachment_names: list[str] | None) -> str:
    if not attachment_names:
        return ""
    return "\n**添付ファイル**: " + ", ".join(attachment_names) + "（添付フォルダに保存）\n"


def append_to_yoritoori(
    folder_path,
    partner_name,
    date_str,
    body,
    source="SMS/iMessage",
    *,
    attachment_names: list[str] | None = None,
):
    md_path = BASE_DIR / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"{YORITOORI_FILENAME} が見つかりません: {md_path}", file=sys.stderr)
        return False

    summary = make_summary(body)
    attach = _attach_block(attachment_names)
    content = md_path.read_text(encoding="utf-8")
    block = f"""

### {date_str}｜{partner_name}｜相手から返信（{source}）｜{summary}

{body}
{attach}
---
"""
    marker = "## やり取り（時系列）"
    if marker in content:
        pos = content.find(marker) + len(marker)
        content = content[:pos].rstrip() + "\n\n" + block.strip() + "\n\n" + content[pos:].lstrip()
    else:
        content += block
    md_path.write_text(content, encoding="utf-8")
    mirror_yoritoori_md_to_gitrepos(md_path)
    return True


def _load_phone_to_partner(partner_filter: str | None = None):
    contact_path = CONTACT_YAML
    if not contact_path.exists():
        raise RuntimeError(f"連絡先一覧が見つかりません: {contact_path}")

    config = yaml.safe_load(contact_path.read_text(encoding="utf-8")) or {}
    partners = config.get("partners", [])
    phone_to_partner = {}
    for p in partners:
        if partner_filter:
            key = partner_filter.lower()
            name = str(p.get("name", "")).lower()
            folder = str(p.get("folder", "")).lower()
            if key not in name and key not in folder:
                continue
        for ph in p.get("phones", []) or []:
            norm = normalize_phone(ph)
            if norm:
                phone_to_partner[norm] = p
    return phone_to_partner


def _resolve_partner(phone_to_partner, handle_id: str):
    norm_handle = normalize_phone(handle_id)
    if not norm_handle:
        return None, norm_handle
    partner = phone_to_partner.get(norm_handle)
    if not partner:
        for norm_ph, p in phone_to_partner.items():
            if norm_handle.endswith(norm_ph) or norm_ph.endswith(norm_handle):
                partner = p
                break
    return partner, norm_handle


def _open_chat_db():
    db_path = CHAT_DB
    if not db_path.exists():
        print(f"エラー: chat.db が見つかりません: {db_path}", file=sys.stderr)
        print("フルディスクアクセスを付与するか、Mac で iMessage を有効にしてください。", file=sys.stderr)
        sys.exit(1)
    try:
        return sqlite3.connect(str(db_path), timeout=5)
    except sqlite3.OperationalError as e:
        print(f"エラー: chat.db に接続できません: {e}", file=sys.stderr)
        print(
            "システム環境設定 → プライバシーとセキュリティ → フルディスクアクセスに Terminal/Cursor を追加してください。",
            file=sys.stderr,
        )
        sys.exit(1)


def _message_body(text, attributed_body) -> str:
    body = (text or "").strip()
    if not body and attributed_body:
        body = try_parse_attributed_body(attributed_body) or ""
    if body.replace("\uFFFD", "").strip() == "":
        return ""
    return body


def backfill_attachments(conn, phone_to_partner, *, limit: int = 500) -> int:
    """
    パートナー電話に紐づく過去メッセージの添付を Stock へコピー。
    MD への新規追記はしない（ファイル補完のみ）。
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT m.ROWID, m.text, m.date, m.attributedBody, h.id
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            JOIN message_attachment_join maj ON maj.message_id = m.ROWID
            WHERE m.is_from_me = 0
            ORDER BY m.date DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        print(f"エラー: バックフィルクエリ失敗: {e}", file=sys.stderr)
        return 0

    # 同一 message が複数行になるため ROWID で一意化
    seen: set[int] = set()
    total = 0
    for rowid, text, date_ns, attributed_body, handle_id in rows:
        if rowid in seen:
            continue
        seen.add(rowid)
        partner, _ = _resolve_partner(phone_to_partner, handle_id)
        if not partner:
            continue
        items = fetch_attachments_for_message(conn, rowid)
        if not items:
            continue
        date_str = format_date_from_apple_ns(date_ns)
        saved = save_imessage_attachments(partner["folder"], date_str, items)
        total += len(saved)
        if saved:
            body_preview = _message_body(text, attributed_body)[:30] or "（添付のみ）"
            print(f"バックフィル: {partner['name']} ({handle_id}) - {body_preview}… → {len(saved)} 件")

    return total


def sync_new_messages(conn, phone_to_partner) -> int:
    max_rowid = load_processed()

    query_with_attr = """
    SELECT m.ROWID, m.text, m.date, m.attributedBody, h.id
    FROM message m
    JOIN handle h ON m.handle_id = h.ROWID
    WHERE m.is_from_me = 0
      AND m.ROWID > ?
    ORDER BY m.date DESC
    LIMIT 100
    """
    query_without_attr = """
    SELECT m.ROWID, m.text, m.date, NULL, h.id
    FROM message m
    JOIN handle h ON m.handle_id = h.ROWID
    WHERE m.is_from_me = 0
      AND m.ROWID > ?
    ORDER BY m.date DESC
    LIMIT 100
    """

    cur = conn.cursor()
    try:
        cur.execute(query_with_attr, (max_rowid,))
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        try:
            cur.execute(query_without_attr, (max_rowid,))
            rows = cur.fetchall()
        except sqlite3.OperationalError as e:
            print(f"エラー: クエリ実行失敗: {e}", file=sys.stderr)
            sys.exit(1)

    appended = 0
    new_max_rowid = max_rowid

    for row in rows:
        rowid, text, date_ns, attributed_body, handle_id = row
        new_max_rowid = max(new_max_rowid, rowid)

        partner, norm_handle = _resolve_partner(phone_to_partner, handle_id)
        if not norm_handle or not partner:
            continue

        body = _message_body(text, attributed_body)
        items = fetch_attachments_for_message(conn, rowid)
        if not body and not items:
            continue
        if not body:
            body = "（添付のみ）"

        date_str = format_date_from_apple_ns(date_ns)
        attachment_names = save_imessage_attachments(partner["folder"], date_str, items)

        ok = append_to_yoritoori(
            partner["folder"],
            partner["name"],
            date_str,
            body,
            attachment_names=attachment_names,
        )
        if ok:
            appended += 1
            print(f"追記: {partner['name']} ({handle_id}) - {body[:40]}...")

    if appended > 0:
        save_processed(new_max_rowid)

    return appended


def main():
    parser = argparse.ArgumentParser(
        description="iMessage/SMS をやり取り.md に追記（添付は受信添付へ保存）"
    )
    parser.add_argument("--partner", help="対象パートナー名またはフォルダ名（部分一致）")
    parser.add_argument(
        "--backfill-attachments",
        action="store_true",
        help="過去メッセージの添付を 1.受信添付(Stock) へ補完（MD 追記なし）",
    )
    parser.add_argument(
        "--backfill-limit",
        type=int,
        default=500,
        help="バックフィルで走査する添付付きメッセージ上限（既定 500）",
    )
    args = parser.parse_args()

    try:
        phone_to_partner = _load_phone_to_partner(args.partner)
    except RuntimeError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    if not phone_to_partner:
        print("連絡先一覧に phones が1件も登録されていません（または --partner に一致なし）。")
        print("連絡先一覧.yaml の phones に電話番号を追加してください。")
        return

    conn = _open_chat_db()
    try:
        if args.backfill_attachments:
            n = backfill_attachments(
                conn, phone_to_partner, limit=max(1, args.backfill_limit)
            )
            print(
                f"\nバックフィル合計: {n} 件の添付を保存しました。"
                if n
                else "\n保存した添付はありませんでした。"
            )
            return

        appended = sync_new_messages(conn, phone_to_partner)
        if appended > 0:
            print(f"\n{appended} 件のメッセージをやり取りに追記しました。")
        else:
            print("連絡先一覧に一致する未読メッセージはありませんでした。")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
