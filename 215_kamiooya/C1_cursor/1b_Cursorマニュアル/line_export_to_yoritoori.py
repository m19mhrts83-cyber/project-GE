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
from dataclasses import dataclass
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
    insert_block_after_timeline_header,
    is_duplicate,
    JST,
    load_processed,
    record_processed,
    save_processed,
)
from yoritoori_utils import format_line_heading


@dataclass(frozen=True)
class ExportTarget:
    folder: str
    display_name: str
    group: bool = False
    group_label: str = ""


@dataclass
class ImportResult:
    status: str  # imported | repaired | skipped_duplicate | empty | error
    folder: str = ""
    md_path: Path | None = None
    heading: str = ""
    message: str = ""
    repaired_count: int = 0
    placeholders_remaining: int = 0
    placeholders_in_md: int = 0
    export_messages: int = 0
    decision: str = ""


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


def parse_export_body(path: Path, *, plain: bool = False) -> tuple[str, datetime | None, str]:
    """(body, latest_dt, parse_note)"""
    if plain:
        return plain_body(path), None, ""
    parsed, err, latest_dt = try_parse_linelog2py(path)
    if parsed is not None:
        return parsed, latest_dt, ""
    body = plain_body(path)
    note = f"（linelog2py 非対応のためプレーン貼り付け: {err}）"
    return body, None, note


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


def target_from_args(args) -> ExportTarget:
    folder, display_name = resolve_folder_name(args)
    gl = (args.group_label or "").strip()
    return ExportTarget(
        folder=folder,
        display_name=display_name,
        group=bool(args.group) or bool(gl),
        group_label=gl,
    )


def build_export_message_blocks(messages: list, target: ExportTarget) -> str:
    """公式エクスポートを CHRLINE と同様、1メッセージ1ブロック・最新が上。"""
    from line_export_placeholder_repair import _format_message_body

    gl = (target.group_label or "").strip()
    is_group = bool(target.group) or bool(gl)
    label = gl or target.display_name
    tag = (
        f"{label}（LINEグループ・公式エクスポート）"
        if is_group
        else "LINE（公式エクスポート）"
    )
    parts: list[str] = []
    for msg in sorted(messages, key=lambda m: m.when, reverse=True):
        body_text = _format_message_body(msg)
        date_part = msg.when.strftime("%Y/%m/%d")
        heading = format_line_heading(
            date_part, target.display_name, tag, body_for_tail=msg.text
        )
        parts.extend(
            [
                heading,
                "",
                "<details>",
                "<summary>本文</summary>",
                "",
                body_text,
                "",
                "</details>",
                "",
                "---",
            ]
        )
    return "\n".join(parts)


def append_export_to_md(
    md_path: Path,
    path: Path,
    target: ExportTarget,
    *,
    plain: bool,
    parsed_messages: list | None,
    body: str,
    latest_dt: datetime | None,
    parse_note: str,
    decision: str,
    dry_run: bool,
) -> tuple[str, str]:
    """追記本体。戻り値: (first_heading, detail_message)"""
    gl = (target.group_label or "").strip()
    is_group = bool(target.group) or bool(gl)
    direction = "receive"

    if parsed_messages and not plain:
        block_md = build_export_message_blocks(parsed_messages, target)
        first_heading = block_md.split("\n", 1)[0]
        detail = f"{decision} — {len(parsed_messages)}件を最新順に追記"
        if dry_run:
            return first_heading, f"[dry-run] {detail}"
        content = md_path.read_text(encoding="utf-8")
        md_path.write_text(
            insert_block_after_timeline_header(content, "\n\n" + block_md + "\n"),
            encoding="utf-8",
        )
        return first_heading, detail

    if parse_note:
        body = f"{parse_note}\n\n{body}"

    if latest_dt is not None:
        date_str = latest_dt.strftime("%Y/%m/%d %H:%M")
    else:
        date_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    heading = build_heading_line(
        date_str,
        target.display_name,
        direction,
        is_group,
        gl if gl else None,
        body,
    )
    detail = decision or "追記"
    if dry_run:
        return heading, f"[dry-run] {detail}"
    append_line_block(md_path, heading, body, direction, None)
    return heading, detail


def import_line_export_file(
    path: Path,
    target: ExportTarget,
    *,
    plain: bool = False,
    no_dedup: bool = False,
    dry_run: bool = False,
    repair_placeholders: bool = True,
    also_append: bool = False,
) -> ImportResult:
    path = path.expanduser().resolve()
    if not path.is_file():
        return ImportResult(status="error", message=f"ファイルがありません: {path}")

    md_path = BASE_PATH / target.folder / YORITOORI_FILENAME
    if not md_path.is_file():
        return ImportResult(
            status="error",
            folder=target.folder,
            message=f"{YORITOORI_FILENAME} がありません: {md_path}",
        )

    repaired_count = 0
    placeholders_remaining = 0
    placeholders_in_md = 0
    export_messages = 0
    decision = ""
    parsed_messages: list | None = None

    if repair_placeholders and not plain:
        from line_export_placeholder_repair import (
            parse_export_messages,
            repair_placeholders_in_content,
        )

        messages, parse_err = parse_export_messages(path)
        parsed_messages = messages or None
        export_messages = len(messages)
        if messages:
            content = md_path.read_text(encoding="utf-8")
            new_content, repair_result = repair_placeholders_in_content(
                content, messages, include_media=False
            )
            repaired_count = repair_result.replaced
            placeholders_remaining = repair_result.skipped_no_match
            placeholders_in_md = repair_result.placeholders_total

            if repaired_count > 0 and not also_append:
                decision = (
                    f"修復 {repaired_count} 件（対象 {placeholders_in_md} 件）"
                    f"→ 追記スキップ（重複防止・自動判定）"
                )
                msg = decision
                if parse_err:
                    msg += f" ※パース: {parse_err}"
                if not dry_run:
                    bak = md_path.with_suffix(md_path.suffix + ".bak-export-repair")
                    if not bak.exists():
                        bak.write_text(content, encoding="utf-8")
                    md_path.write_text(new_content, encoding="utf-8")
                return ImportResult(
                    status="repaired",
                    folder=target.folder,
                    md_path=md_path,
                    message=msg if not dry_run else f"[dry-run] {msg}",
                    repaired_count=repaired_count,
                    placeholders_remaining=placeholders_remaining,
                    placeholders_in_md=placeholders_in_md,
                    export_messages=export_messages,
                    decision=decision,
                )

            if placeholders_in_md == 0:
                decision = "修復対象プレースホルダーなし → 全文追記（自動判定）"
            elif repaired_count == 0:
                decision = (
                    f"修復 0 件（対象 {placeholders_in_md} 件・日付不一致等）"
                    f"→ 全文追記（自動判定）"
                )
            else:
                decision = "修復後も追記（--also-append）"

    if not parsed_messages and not plain:
        from line_export_placeholder_repair import parse_export_messages

        messages, _ = parse_export_messages(path)
        parsed_messages = messages or None
        export_messages = len(messages)

    body, latest_dt, parse_note = parse_export_body(path, plain=plain)
    if not body.strip() and not parsed_messages:
        return ImportResult(status="empty", message="本文が空です")

    gl = (target.group_label or "").strip()
    is_group = bool(target.group) or bool(gl)
    direction = "receive"

    body_hash = sha256(body.encode("utf-8")).hexdigest()
    pdata = load_processed()
    if not no_dedup and is_duplicate(pdata, target.folder, direction, body_hash):
        return ImportResult(
            status="skipped_duplicate",
            folder=target.folder,
            md_path=md_path,
            message="同一内容を直近ですでに追記済み",
        )

    if parsed_messages and not plain and decision and "追記" in decision:
        decision = decision.replace("全文追記", f"{len(parsed_messages)}件を最新順に追記")

    heading, detail = append_export_to_md(
        md_path,
        path,
        target,
        plain=plain,
        parsed_messages=parsed_messages,
        body=body,
        latest_dt=latest_dt,
        parse_note=parse_note,
        decision=decision,
        dry_run=dry_run,
    )

    if dry_run:
        return ImportResult(
            status="imported",
            folder=target.folder,
            md_path=md_path,
            heading=heading,
            message=detail,
            decision=decision or detail.replace("[dry-run] ", ""),
            placeholders_in_md=placeholders_in_md,
            export_messages=export_messages,
        )

    record_processed(pdata, target.folder, direction, body_hash)
    save_processed(pdata)

    return ImportResult(
        status="imported",
        folder=target.folder,
        md_path=md_path,
        heading=heading,
        message=f"追記しました: {md_path}（{detail}）",
        decision=decision or detail,
        placeholders_in_md=placeholders_in_md,
        export_messages=export_messages,
    )


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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-repair", action="store_true", help="プレースホルダー in-place 修復をしない")
    parser.add_argument("--also-append", action="store_true", help="修復後も全文を追記する")
    args = parser.parse_args()

    path = args.export_file.expanduser()
    target = target_from_args(args)
    result = import_line_export_file(
        path,
        target,
        plain=bool(args.plain),
        no_dedup=bool(args.no_dedup),
        dry_run=bool(args.dry_run),
        repair_placeholders=not args.no_repair,
        also_append=bool(args.also_append),
    )

    if result.status == "error":
        print(f"エラー: {result.message}", file=sys.stderr)
        sys.exit(1)
    if result.status == "empty":
        print(f"エラー: {result.message}", file=sys.stderr)
        sys.exit(1)
    if result.status == "skipped_duplicate":
        print(result.message)
        return
    if result.status == "repaired":
        print(result.message)
        return

    print(result.message)
    if result.heading:
        h = result.heading
        print(f"  {h[:100]}{'…' if len(h) > 100 else ''}")


if __name__ == "__main__":
    main()
