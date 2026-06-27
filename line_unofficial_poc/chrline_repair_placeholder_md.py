#!/usr/bin/env python3
"""
既存 5.やり取り.md のプレースホルダーブロックを CHRLINE API で再取得し in-place 差し替えする。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from chrline_client_utils import build_logged_in_client, save_root_from_env
from chrline_md_block_utils import (
    YoritooriBlock,
    build_yoritoori_block,
    find_placeholder_blocks,
    replace_block_at,
)
from chrline_message_fetch import fetch_messages_deep, group_fetch_mid
from chrline_sync_delta_poc import (
    _format_line_msg_when,
    _msg_body_line_with_e2ee_register,
    _msg_sender_mid,
    _msg_time,
)
from chrline_sync_to_yoritoori import (
    DEDUP_FILENAME,
    _default_kamiooya_kanji_yoritoori_path,
    _default_leaf_yoritoori_path,
    _default_tcell_yoritoori_path,
    _is_textual_body,
    _load_dedup,
    _load_retry_queue,
    _message_dedup_key,
    _resolve_group_mid_by_title,
    _save_dedup,
)


def _line_default_md_paths() -> list[Path]:
    return [
        _default_tcell_yoritoori_path(),
        _default_leaf_yoritoori_path(),
        _default_kamiooya_kanji_yoritoori_path(),
    ]


def _backup_md(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    dest = path.with_name(f"{path.name}.bak-{ts}")
    shutil.copy2(path, dest)
    return dest


def _decode_messages(
    cl,
    msgs: list,
    *,
    fetch_mid: str | None,
    e2ee_registered: set[str],
    receive_only: bool,
    my_mid: str,
) -> list[tuple[int, str, str, str | None, bool]]:
    """(ts, date_part, body, dk, is_send)"""
    out: list[tuple[int, str, str, str | None, bool]] = []
    for msg in msgs:
        ts = _msg_time(cl, msg) or 0
        when = _format_line_msg_when(ts)
        date_part = when.split()[0] if when and " " in when else when or "?"
        sender = (_msg_sender_mid(cl, msg) or "").strip()
        is_send = bool(my_mid and sender and sender == my_mid)
        if receive_only and is_send:
            continue
        body = _msg_body_line_with_e2ee_register(
            cl,
            msg,
            None,
            e2ee_registered,
            skip_register=False,
            fetch_chat_mid=fetch_mid,
        )
        if not _is_textual_body(body):
            continue
        dk = _message_dedup_key(cl, msg)
        out.append((ts, date_part, body, dk, is_send))
    return out


def _match_blocks_to_messages(
    blocks: list[YoritooriBlock],
    decoded: list[tuple[int, str, str, str | None, bool]],
) -> list[tuple[YoritooriBlock, str, str]]:
    dk_map: dict[str, str] = {}
    for _ts, _dp, body, dk, _is_send in decoded:
        if dk and dk not in dk_map:
            dk_map[dk] = body

    results: list[tuple[YoritooriBlock, str, str]] = []
    used_dk: set[str] = set()
    remaining: list[YoritooriBlock] = []

    for block in blocks:
        if block.dk and block.dk in dk_map:
            results.append((block, dk_map[block.dk], block.dk))
            used_dk.add(block.dk)
        else:
            remaining.append(block)

    by_date_blocks: dict[str, list[YoritooriBlock]] = defaultdict(list)
    for b in remaining:
        by_date_blocks[b.date_part].append(b)

    by_date_msgs: dict[str, list[tuple[int, str, str | None]]] = defaultdict(list)
    for ts, dp, body, dk, _is_send in decoded:
        if dk and dk in used_dk:
            continue
        by_date_msgs[dp].append((ts, body, dk))

    for date_part, blist in by_date_blocks.items():
        msgs_sorted = sorted(by_date_msgs.get(date_part, []), key=lambda x: x[0])
        for i, block in enumerate(blist):
            if i >= len(msgs_sorted):
                break
            _ts, body, dk = msgs_sorted[i]
            dk_s = dk or ""
            if dk_s and dk_s in used_dk:
                continue
            results.append((block, body, dk_s))
            if dk_s:
                used_dk.add(dk_s)

    return results


def repair_md_file(
    cl,
    *,
    md_path: Path,
    chat_mid: str,
    fetch_depth: int,
    dry_run: bool,
    receive_only: bool,
    seen_keys: set[str],
    verbose: bool,
) -> dict:
    text = md_path.read_text(encoding="utf-8")
    blocks = find_placeholder_blocks(text)
    if not blocks:
        return {"path": str(md_path), "placeholder": 0, "repaired": 0, "failed": 0}

    fetch_mid = group_fetch_mid(chat_mid)
    e2ee_registered: set[str] = set()
    if fetch_mid:
        try:
            cl.tryRegisterE2EEGroupKey(fetch_mid)
            e2ee_registered.add(fetch_mid)
        except Exception:
            pass

    my_mid = (getattr(cl, "mid", None) or "").strip()
    msgs = fetch_messages_deep(
        cl,
        chat_mid,
        fetch_depth,
        skip_e2ee_key_register=False,
    )
    decoded = _decode_messages(
        cl,
        msgs,
        fetch_mid=fetch_mid,
        e2ee_registered=e2ee_registered,
        receive_only=receive_only,
        my_mid=my_mid,
    )

    pairs = _match_blocks_to_messages(blocks, decoded)
    repaired = 0
    failed = len(blocks) - len(pairs)
    content = text

    for block, body, dk in sorted(pairs, key=lambda x: x[0].start, reverse=True):
        new_block = build_yoritoori_block(
            date_part=block.date_part,
            org_label=block.org_label,
            tag=block.tag,
            body=body,
            dk=dk or None,
        )
        if dry_run:
            if verbose:
                print(f"[dry-run] repair {md_path.name} {block.date_part} {block.tag[:30]}…", file=sys.stderr)
        else:
            content = replace_block_at(content, block, new_block)
            if dk:
                seen_keys.add(dk)
        repaired += 1

    if not dry_run and repaired:
        md_path.write_text(content, encoding="utf-8")

    return {
        "path": str(md_path),
        "placeholder": len(blocks),
        "repaired": repaired,
        "failed": max(0, len(blocks) - repaired),
    }


def _resolve_targets_for_repair(args: argparse.Namespace, cl) -> list[tuple[Path, str]]:
    """(md_path, chat_mid) の修復対象。"""
    out: list[tuple[Path, str]] = []
    gneedle = (args.group_chat_mid or "").strip() or (__import__("os").environ.get("LINE_TCELL_GROUP_CHAT_MID") or "").strip()
    if not gneedle:
        gneedle = _resolve_group_mid_by_title(cl, (args.group_title or "").strip()) or ""
    if gneedle:
        out.append((_default_tcell_yoritoori_path(), gneedle))

    lneedle = (args.leaf_group_chat_mid or "").strip() or (__import__("os").environ.get("LINE_LEAF_GROUP_CHAT_MID") or "").strip()
    if not lneedle:
        lneedle = _resolve_group_mid_by_title(cl, (args.leaf_group_title or "").strip()) or ""
    if lneedle:
        out.append((_default_leaf_yoritoori_path(), lneedle))

    kk = (args.kamiooya_kanji_group_chat_mid or "").strip() or (
        __import__("os").environ.get("LINE_KAMIOOYA_KANJI_GROUP_CHAT_MID") or ""
    ).strip()
    if not kk:
        kk = _resolve_group_mid_by_title(cl, (args.kamiooya_kanji_group_title or "").strip()) or ""
    if kk:
        out.append((_default_kamiooya_kanji_yoritoori_path(), kk))

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="5.やり取り.md プレースホルダー in-place 修復")
    parser.add_argument("--preset", choices=("line-default",), default="line-default")
    parser.add_argument("--md", type=Path, action="append", default=[])
    parser.add_argument("--fetch-depth", type=int, default=1500)
    parser.add_argument("--backup", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--allow-qr-login", action="store_true")
    parser.add_argument("--include-send", action="store_true")
    parser.add_argument("--group-chat-mid", default="")
    parser.add_argument("--group-title", default="キャラメル管理G")
    parser.add_argument("--leaf-group-chat-mid", default="")
    parser.add_argument("--leaf-group-title", default="Grandole志賀本通")
    parser.add_argument("--kamiooya-kanji-group-chat-mid", default="")
    parser.add_argument("--kamiooya-kanji-group-title", default="東海飲み会幹事やりとり")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root, allow_qr_login=bool(args.allow_qr_login))

    targets = _resolve_targets_for_repair(args, cl)
    if args.md:
        for p in args.md:
            targets.append((p.expanduser().resolve(), ""))

    if not targets:
        print("修復対象の chatMid を解決できませんでした。", file=sys.stderr)
        return 1

    dedup_path = save_root / DEDUP_FILENAME
    seen_keys = _load_dedup(dedup_path)
    queue = _load_retry_queue(save_root / ".chrline_sync_retry_queue.json")
    _ = queue  # 将来 dk 突合用

    reports: list[dict] = []
    receive_only = not args.include_send

    for md_path, chat_mid in targets:
        if not md_path.is_file():
            print(f"スキップ（ファイルなし）: {md_path}", file=sys.stderr)
            continue
        if not chat_mid:
            print(f"スキップ（chatMid なし）: {md_path}", file=sys.stderr)
            continue
        if args.backup and not args.dry_run:
            bak = _backup_md(md_path)
            print(f"バックアップ: {bak}", file=sys.stderr)
        rep = repair_md_file(
            cl,
            md_path=md_path,
            chat_mid=chat_mid,
            fetch_depth=int(args.fetch_depth),
            dry_run=bool(args.dry_run),
            receive_only=receive_only,
            seen_keys=seen_keys,
            verbose=bool(args.verbose),
        )
        reports.append(rep)
        print(
            f"{md_path.parent.name}: placeholder={rep['placeholder']} repaired={rep['repaired']} failed={rep['failed']}"
        )

    if not args.dry_run and seen_keys:
        _save_dedup(dedup_path, seen_keys)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": bool(args.dry_run),
        "reports": reports,
        "total_repaired": sum(r["repaired"] for r in reports),
        "total_failed": sum(r["failed"] for r in reports),
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
