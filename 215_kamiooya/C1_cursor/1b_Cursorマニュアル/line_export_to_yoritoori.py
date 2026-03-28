#!/usr/bin/env python3
"""
LINE 公式アプリの「トーク履歴の送信／エクスポート」で得た .txt を読み、
5.やり取り.md に追記する（フェーズC・履歴取り込み優先ルート）。

形式が linelog2py（Reader.readFile）に合えば日時・発言者付きで整形する。
合わない場合はファイル全文をプレーン本文として追記する。

前提:
  - pip install PyYAML linelog2py（.venv_gmail 推奨）
  - 連絡先一覧.yaml・line_to_yoritoori_clip.py と同じパス解決

使い方:
  python line_export_to_yoritoori.py --export-file ~/Downloads/chat.txt --partner Tcell --group --group-label "キャラメル管理G"
  python line_export_to_yoritoori.py --export-file ./export.txt --folder 103_Tcell --plain
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import yaml

from line_to_yoritoori_clip import (
    BASE_PATH,
    CONTACT_PATH,
    YORITOORI_FILENAME,
    append_line_block,
    build_heading_line,
    find_partner,
    is_duplicate,
    JST,
    load_processed,
    record_processed,
    save_processed,
)
def try_parse_linelog2py(path: Path) -> tuple[str | None, str, datetime | None]:
    """
    linelog2py でパース試行。
    戻り値: (整形本文, エラー文字列または "", 最新メッセージ時刻または None)
    """
    try:
        from linelog2py.reader import Reader
    except ImportError:
        return None, "linelog2py が未インストール（pip install linelog2py）", None

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="utf-8", errors="replace")

    tmp = path.with_suffix(path.suffix + ".utf8tmp")
    try:
        tmp.write_text(raw, encoding="utf-8")
        messages = Reader.readFile(str(tmp))
    except Exception as e:
        return None, str(e), None
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    if not messages:
        return None, "メッセージ0件", None

    lines = []
    for m in messages:
        ts = m.time.strftime("%Y/%m/%d %H:%M")
        user = (m.username or "").strip() or "（名前なし）"
        text = " ".join(m.textlines).strip()
        lines.append(f"{ts}  {user}  {text}")
    body = "\n".join(lines)
    latest = max(m.time for m in messages)
    return body, "", latest


def plain_body(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def resolve_folder_name(args) -> tuple[str, str]:
    if not CONTACT_PATH.exists():
        print(f"エラー: 連絡先一覧が見つかりません: {CONTACT_PATH}", file=sys.stderr)
        sys.exit(1)
    config = yaml.safe_load(CONTACT_PATH.read_text(encoding="utf-8")) or {}
    partners = config.get("partners", [])
    if args.folder:
        return args.folder.strip(), (args.display_name or args.folder).strip()
    partner = find_partner(partners, args.partner)
    if not partner:
        print(f"エラー: パートナー '{args.partner}' が見つかりません。", file=sys.stderr)
        sys.exit(1)
    return partner["folder"], partner.get("name") or partner["folder"]


def main() -> None:
    parser = argparse.ArgumentParser(description="LINE 公式エクスポート .txt を 5.やり取り.md に追記")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--partner", help="連絡先一覧の name または folder")
    g.add_argument("--folder", help="追記先フォルダ名")
    parser.add_argument("--display-name", help="--folder 時の見出し名")
    parser.add_argument("--export-file", required=True, type=Path, help="LINE が出力した .txt のパス")
    parser.add_argument("--group", action="store_true", help="グループ用見出し")
    parser.add_argument("--group-label", help="グループ名・案件名（要約の先頭）")
    parser.add_argument("--plain", action="store_true", help="linelog2py を使わず全文をそのまま本文にする")
    parser.add_argument("--no-dedup", action="store_true")
    args = parser.parse_args()

    path = args.export_file.expanduser()
    if not path.is_file():
        print(f"エラー: ファイルがありません: {path}", file=sys.stderr)
        sys.exit(1)

    latest_dt: datetime | None = None
    if args.plain:
        body = plain_body(path)
        parse_note = ""
    else:
        parsed, err, latest_dt = try_parse_linelog2py(path)
        if parsed is not None:
            body = parsed
            parse_note = ""
        else:
            body = plain_body(path)
            parse_note = f"（linelog2py 非対応のためプレーン貼り付け: {err}）"

    if not body.strip():
        print("エラー: 本文が空です。", file=sys.stderr)
        sys.exit(1)

    if parse_note:
        body = f"{parse_note}\n\n{body}"

    folder, display_name = resolve_folder_name(args)
    md_path = BASE_PATH / folder / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"エラー: {YORITOORI_FILENAME} がありません: {md_path}", file=sys.stderr)
        sys.exit(1)

    gl = (args.group_label or "").strip()
    is_group = bool(args.group) or bool(gl)
    direction = "receive"

    body_hash = sha256(body.encode("utf-8")).hexdigest()
    pdata = load_processed()
    if not args.no_dedup and is_duplicate(pdata, folder, direction, body_hash):
        print("同一内容を直近ですでに追記済みのためスキップ（--no-dedup で再追記可）。")
        return

    if latest_dt is not None:
        date_str = latest_dt.strftime("%Y/%m/%d %H:%M")
    else:
        date_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    heading = build_heading_line(
        date_str,
        display_name,
        direction,
        is_group,
        gl if gl else None,
        body,
    )

    append_line_block(md_path, heading, body, direction, None)
    record_processed(pdata, folder, direction, body_hash)
    save_processed(pdata)

    print(f"追記しました: {md_path}")
    print(f"  {heading[:100]}{'…' if len(heading) > 100 else ''}")


if __name__ == "__main__":
    main()
