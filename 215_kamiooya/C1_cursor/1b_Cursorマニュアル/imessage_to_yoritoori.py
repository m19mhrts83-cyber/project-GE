#!/usr/bin/env python3
"""
Mac の iMessage/SMS（chat.db）から受信メッセージを取得し、
連絡先一覧の phones と照合して該当フォルダの やり取り.md に追記する。

前提:
  - Mac で iMessage が有効で、iPhone と同期されていること
  - フルディスクアクセスを Terminal/Cursor に付与済み
  - 連絡先一覧.yaml の phones に電話番号を登録済み
  - pip install -r requirements_gmail.txt 済み（PyYAML 使用）

使い方: python imessage_to_yoritoori.py
"""

import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import yaml

# 設定
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent.parent / "C2_ルーティン作業" / "26_パートナー社への相談"
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
        # 16進数文字列の場合
        if isinstance(blob, bytes):
            text = blob.decode("utf-8", errors="ignore")
        else:
            text = str(blob)
        # よくあるパターン: NSString の後に引用可能なテキスト
        m = re.search(r'NSString[^"]*"([^"]*)"', text)
        if m:
            return m.group(1).strip()
        # 16進ダンプから ASCII 抽出を試す
        ascii_match = re.findall(r"[\x20-\x7e]{4,}", text)
        if ascii_match:
            return " ".join(ascii_match[:5]).strip()
    except Exception:
        pass
    return None


def append_to_yoritoori(folder_path, partner_name, date_str, body, source="SMS/iMessage"):
    from yoritoori_utils import make_summary, YORITOORI_FILENAME

    md_path = BASE_DIR / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"{YORITOORI_FILENAME} が見つかりません: {md_path}", file=sys.stderr)
        return False

    summary = make_summary(body)
    content = md_path.read_text(encoding="utf-8")
    block = f"""

### {date_str}｜{partner_name}｜相手から返信（{source}）｜{summary}

{body}

---
"""
    # 新しいメッセージを上に表示（時系列で新しい順）
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


def main():
    contact_path = CONTACT_YAML
    base_path = BASE_DIR

    if not contact_path.exists():
        print(f"エラー: 連絡先一覧が見つかりません: {contact_path}", file=sys.stderr)
        sys.exit(1)

    config = yaml.safe_load(contact_path.read_text(encoding="utf-8"))
    partners = config.get("partners", [])

    phone_to_partner = {}
    for p in partners:
        for ph in p.get("phones", []):
            norm = normalize_phone(ph)
            if norm:
                phone_to_partner[norm] = p

    if not phone_to_partner:
        print("連絡先一覧に phones が1件も登録されていません。")
        print("連絡先一覧.yaml の phones に電話番号を追加してください。")
        return

    db_path = CHAT_DB
    if not db_path.exists():
        print(f"エラー: chat.db が見つかりません: {db_path}", file=sys.stderr)
        print("フルディスクアクセスを付与するか、Mac で iMessage を有効にしてください。", file=sys.stderr)
        sys.exit(1)

    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
    except sqlite3.OperationalError as e:
        print(f"エラー: chat.db に接続できません: {e}", file=sys.stderr)
        print("システム環境設定 → プライバシーとセキュリティ → フルディスクアクセスに Terminal/Cursor を追加してください。", file=sys.stderr)
        sys.exit(1)

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
            conn.close()
            sys.exit(1)

    appended = 0
    new_max_rowid = max_rowid

    for row in rows:
        rowid, text, date_ns, attributed_body, handle_id = row
        new_max_rowid = max(new_max_rowid, rowid)

        norm_handle = normalize_phone(handle_id)
        partner = phone_to_partner.get(norm_handle)
        if not partner:
            for norm_ph, p in phone_to_partner.items():
                if norm_handle.endswith(norm_ph) or norm_ph.endswith(norm_handle):
                    partner = p
                    break
        if not partner:
            continue

        body = (text or "").strip()
        if not body and attributed_body:
            body = try_parse_attributed_body(attributed_body) or ""
        if not body:
            continue

        date_str = format_date_from_apple_ns(date_ns)

        ok = append_to_yoritoori(partner["folder"], partner["name"], date_str, body)
        if ok:
            appended += 1
            log_msg = f"追記: {partner['name']} ({handle_id}) - {body[:40]}..."
            print(log_msg)

    conn.close()

    if appended > 0:
        save_processed(new_max_rowid)
        print(f"\n{appended} 件のメッセージをやり取りに追記しました。")
    else:
        print("連絡先一覧に一致する未読メッセージはありませんでした。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
