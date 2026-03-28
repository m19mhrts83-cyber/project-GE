#!/usr/bin/env python3
"""
特定の電話番号（iMessage/SMS の handle.id）に紐づくメッセージのみを抽出し、
指定フォルダ（例: 311_グッドウィン）の `5.やり取り.md` に追記する。

目的:
- `imessage_processed.json` の max_rowid に依存せず、「今までのやり取り」をバックフィルする。
- 他パートナーの重複追記を避けるため、電話番号単位で処理する。

使い方例:
  python imessage_export_phone_to_yoritoori.py --phone 09033005040 --base-dir "…/26_パートナー社への相談" --limit 5000
  python imessage_export_phone_to_yoritoori.py --phone 09033005040 --base-dir "…/26_パートナー社への相談" --include-sent --limit 5000
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from yoritoori_utils import YORITOORI_FILENAME, make_summary


def normalize_phone(phone: str) -> str:
    """電話番号を数字のみに正規化。09012345678 と +819012345678 を統一。"""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("81") and len(digits) > 10:
        return digits  # +81...
    if (digits.startswith("0") and len(digits) == 10) or (digits.startswith("0") and len(digits) == 11):
        return "81" + digits.lstrip("0")
    return digits


@dataclass
class PartnerInfo:
    folder: str
    name: str


def format_date_from_apple_ns(ns) -> str:
    """Apple の日付（ナノ秒、2001-01-01 からの経過）を YYYY/MM/DD HH:MM に変換。"""
    if ns is None:
        return datetime.now().strftime("%Y/%m/%d %H:%M")
    try:
        sec = int(ns) / 1_000_000_000 + 978307200
        dt = datetime.fromtimestamp(sec)
        return dt.strftime("%Y/%m/%d %H:%M")
    except (ValueError, OSError, OverflowError):
        return datetime.now().strftime("%Y/%m/%d %H:%M")


def try_parse_attributed_body(blob):
    """attributedBody からテキストを抽出を試す。失敗時は None。"""
    if not blob:
        return None
    try:
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


def is_probably_garbled(s: str) -> bool:
    """取り込み時に出やすい「文字化け/バイナリダンプっぽい」本文かどうか判定。"""
    if not s:
        return False
    # よくあるダンプ断片
    if (
        "#$_" in s
        or "NS.rangeval" in s
        or "streamtyped" in s
        or "NSAttributedString" in s
        or "$classnameX" in s
        or "NSString" in s
        or "NSObject" in s
        or "NSValue" in s
        or "NS.objects" in s
        or re.search(r"\bNS\.", s) is not None
    ):
        return True
    # 制御文字が混ざっている場合は怪しい
    ctrl = 0
    for ch in s:
        o = ord(ch)
        if o in (10, 13, 9):  # \n, \r, \t は許容
            continue
        if o < 32:
            ctrl += 1
    return ctrl > 0


def choose_body(text_body: str, attributed_body) -> str:
    """text がダンプっぽい場合は attributedBody を優先して本文を決める。"""
    text_body = (text_body or "").strip()
    attr_parsed = try_parse_attributed_body(attributed_body) if attributed_body else None
    if not text_body:
        return (attr_parsed or "").strip()
    if is_probably_garbled(text_body):
        # attributedBody 側で復元できる場合のみ採用（できないならスキップするため空を返す）
        if attr_parsed and not is_probably_garbled(attr_parsed):
            return attr_parsed.strip()
        return ""
    return text_body


def load_partners(contact_yaml: Path, phone_norm: str) -> PartnerInfo | None:
    config = yaml.safe_load(contact_yaml.read_text(encoding="utf-8"))
    for p in config.get("partners", []):
        for ph in p.get("phones", []) or []:
            if not ph:
                continue
            # imessage_to_yoritoori.py と同じ正規化挙動に寄せる
            if normalize_phone(ph) == phone_norm:
                return PartnerInfo(folder=p["folder"], name=p.get("name") or p["folder"])
            # 末尾一致も許容（例: -区切り差）
            if normalize_phone(ph).endswith(phone_norm) or phone_norm.endswith(normalize_phone(ph)):
                return PartnerInfo(folder=p["folder"], name=p.get("name") or p["folder"])
    return None


def append_block(md_path: Path, partner_name: str, date_str: str, direction: str, body: str, is_sent: bool):
    """`5.やり取り.md` の時系列末尾/先頭へ追記（既存スキーマに合わせる）。"""
    summary = make_summary(body)
    label = "自分から送信" if is_sent else "相手から返信"
    block = f"""

### {date_str}｜{partner_name}｜{label}｜{summary}

{body}

---
"""
    content = md_path.read_text(encoding="utf-8")
    marker = "## やり取り（時系列）"
    if marker in content:
        pos = content.find(marker) + len(marker)
        content = content[:pos].rstrip() + "\n\n" + block.strip() + "\n\n" + content[pos:].lstrip()
    else:
        content += block
    md_path.write_text(content, encoding="utf-8")


def reset_md_after_marker(md_path: Path) -> None:
    """`## やり取り（時系列）` 以降を消して、ヘッダだけ残す。"""
    content = md_path.read_text(encoding="utf-8")
    marker = "## やり取り（時系列）"
    if marker not in content:
        md_path.write_text(content + "\n\n" + marker + "\n", encoding="utf-8")
        return
    pos = content.find(marker)
    keep = content[: pos + len(marker)]
    md_path.write_text(keep.rstrip() + "\n\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="特定電話番号の iMessage/SMS を 5.やり取り.md に追記")
    ap.add_argument("--phone", required=True, help="電話番号（例: 09033005040 / 090-3300-5040）")
    ap.add_argument("--base-dir", required=True, help="`26_パートナー社への相談` フォルダへのパス")
    ap.add_argument("--limit", type=int, default=5000, help="最大取得件数（新しい順）")
    ap.add_argument("--include-sent", action="store_true", help="自分から送信も含める（やり取り.md へ追記）")
    ap.add_argument("--reset-md", action="store_true", help="5.やり取り.md の既存本文（時系列以降）を作り直す")
    args = ap.parse_args()

    base_dir = Path(args.base_dir)
    contact_yaml = base_dir / "000_共通" / "連絡先一覧.yaml"
    if not contact_yaml.exists():
        raise SystemExit(f"連絡先一覧がありません: {contact_yaml}")

    phone_norm = normalize_phone(args.phone)
    if not phone_norm:
        raise SystemExit("電話番号の正規化に失敗しました。--phone を確認してください。")

    partner = load_partners(contact_yaml, phone_norm)
    if not partner:
        raise SystemExit("連絡先一覧.yaml に指定 phone が登録されていません。phones の登録を確認してください。")

    md_path = base_dir / partner.folder / YORITOORI_FILENAME
    if not md_path.exists():
        raise SystemExit(f"5.やり取り.md がありません: {md_path}")

    if args.reset_md:
        reset_md_after_marker(md_path)

    chat_db = Path.home() / "Library" / "Messages" / "chat.db"
    if not chat_db.exists():
        raise SystemExit(f"chat.db がありません: {chat_db}")

    allow_is_from_me = (0, 1) if args.include_sent else (0,)

    conn = sqlite3.connect(str(chat_db), timeout=5)
    try:
        # handle テーブルから該当 handle ROWID を抽出
        cur = conn.cursor()
        cur.execute("SELECT ROWID, id FROM handle")
        handle_rows = cur.fetchall()

        matched_handle_rowids = []
        for rowid, hid in handle_rows:
            if not hid:
                continue
            hid_norm = normalize_phone(str(hid))
            if not hid_norm:
                continue
            if hid_norm == phone_norm:
                matched_handle_rowids.append(rowid)
            else:
                # 末尾一致でも拾う
                if hid_norm.endswith(phone_norm) or phone_norm.endswith(hid_norm):
                    matched_handle_rowids.append(rowid)

        if not matched_handle_rowids:
            print("指定 phone に一致する handle が見つかりませんでした。")
            return

        placeholders = ",".join("?" for _ in matched_handle_rowids)
        is_from_me_placeholders = ",".join("?" for _ in allow_is_from_me)

        # 新しい順に limit 件取得（大きい場合の安全策）
        query = f"""
            SELECT m.ROWID, m.text, m.date, m.attributedBody, m.is_from_me, h.id
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.is_from_me IN ({is_from_me_placeholders})
              AND m.handle_id IN ({placeholders})
            ORDER BY m.date DESC
            LIMIT ?
        """
        params = [*allow_is_from_me, *matched_handle_rowids, int(args.limit)]
        rows = cur.execute(query, params).fetchall()

        # 重複対策（簡易）: md 側にある直近エントリを date + 方向 + body冒頭で照合
        existing = set()
        md_content = md_path.read_text(encoding="utf-8")
        for line in md_content.splitlines():
            m = re.match(r"^### (\d{4}/\d{2}/\d{2}(?: \d{2}:\d{2})?)｜[^｜]+｜(相手から返信|自分から送信)｜", line)
            if m:
                # summary 部分は取りにくいので、dateと方向だけをキーにする
                existing.add((m.group(1), m.group(2)))

        appended = 0
        # md は先頭に突っ込むため、取得順（新しい順）をそのまま入れると逆順になる可能性がある
        # -> date 昇順にして時系列らしくする
        rows_sorted = sorted(rows, key=lambda r: r[2] or 0)

        for rowid, text, date_ns, attributed_body, is_from_me, _hid in rows_sorted:
            body = choose_body(text or "", attributed_body)
            if not body:
                continue
            # 本文確定後にも最終チェック（ここでダンプっぽければスキップ）
            if is_probably_garbled(body):
                continue
            if body.replace("\uFFFD", "").strip() == "":
                continue

            date_str = format_date_from_apple_ns(date_ns)
            is_sent = is_from_me == 1
            direction_label = "自分から送信" if is_sent else "相手から返信"

            # 簡易重複判定
            if (date_str, direction_label) in existing:
                continue

            # 追記（先頭挿入）
            append_block(
                md_path=md_path,
                partner_name=partner.name,
                date_str=date_str,
                direction=direction_label,
                body=body,
                is_sent=is_sent,
            )
            appended += 1

            # 記録を更新
            existing.add((date_str, direction_label))

        print(f"追記しました: {appended} 件（phone={args.phone} / folder={partner.folder}）")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

