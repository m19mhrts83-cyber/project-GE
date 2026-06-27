#!/usr/bin/env python3
"""
Gmail 着信の LINE 公式トーク履歴メールから .txt 添付を取り出し、
000_共通/LINE公式エクスポート/inbox/ へ保存する（Phase C 段階3）。

スマホの「トーク履歴を送信」→ 自分宛メール → 本スクリプト → inbox → line_export_inbox_to_yoritoori.py

使い方:
  python line_export_gmail_to_inbox.py
  python line_export_gmail_to_inbox.py --dry-run
  python line_export_gmail_to_inbox.py --days 30
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from gmail_to_yoritoori import (
    SCRIPT_DIR,
    build_service_for_token,
    collect_attachment_parts,
    sanitize_filename,
)
from line_export_inbox_to_yoritoori import default_inbox_dir, default_routes_path

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_STATE = Path.home() / ".cursor" / "line_export_gmail_fetched.json"
ROUTINE_MARKER = "LINE公式エクスポート Gmail取り込み（定常）"

DEFAULT_GMAIL_QUERY = (
    'has:attachment (filename:txt OR filename:zip OR filename:text) '
    '(from:line.naver.jp OR from:notify.line.me OR from:line.me OR from:linecorp.com OR '
    'subject:トーク履歴 OR subject:"Talk History" OR subject:"[LINE]" OR subject:"LINE トーク")'
)

DEFAULT_GMAIL_ACCOUNT = "matsuno.estate@gmail.com"
DEFAULT_GMAIL_TOKEN = "token_estate.json"


@dataclass
class GmailFetchStats:
    scanned: int = 0
    saved: int = 0
    skipped: int = 0
    account: str = ""
    query: str = ""
    files: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def load_gmail_config(routes_path: Path) -> dict:
    if not routes_path.is_file():
        return {}
    data = yaml.safe_load(routes_path.read_text(encoding="utf-8")) or {}
    g = data.get("gmail") if isinstance(data, dict) else None
    return g if isinstance(g, dict) else {}


def resolve_gmail_token_path(cfg: dict) -> Path | None:
    raw = (
        cfg.get("token_file")
        or os.environ.get("LINE_EXPORT_GMAIL_TOKEN")
        or DEFAULT_GMAIL_TOKEN
    ).strip()
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = SCRIPT_DIR / raw
    return p if p.is_file() else None


def expected_gmail_account(cfg: dict) -> str:
    return (
        cfg.get("account")
        or os.environ.get("LINE_EXPORT_GMAIL_ACCOUNT")
        or DEFAULT_GMAIL_ACCOUNT
    ).strip()


def build_query(cfg: dict, days: int) -> str:
    base = (cfg.get("query") or os.environ.get("LINE_EXPORT_GMAIL_QUERY") or DEFAULT_GMAIL_QUERY).strip()
    extra = (cfg.get("query_extra") or "").strip()
    q = base
    if extra:
        q = f"{q} {extra}"
    if days > 0:
        q = f"{q} newer_than:{days}d"
    return q


def load_state(path: Path) -> dict:
    if not path.is_file():
        return {"messages": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("messages"), dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"messages": {}}


def save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def unique_dest(dest_dir: Path, name: str) -> Path:
    dest = dest_dir / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    n = 2
    while True:
        candidate = dest_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def message_date_jst(headers: list[dict]) -> str:
    for h in headers:
        if h.get("name", "").lower() == "date":
            try:
                dt = parsedate_to_datetime(h.get("value", ""))
                if dt.tzinfo:
                    dt = dt.astimezone(JST)
                else:
                    dt = dt.replace(tzinfo=JST)
                return dt.strftime("%Y%m%d")
            except (TypeError, ValueError, OverflowError):
                break
    return datetime.now(JST).strftime("%Y%m%d")


def subject_from_headers(headers: list[dict]) -> str:
    for h in headers:
        if h.get("name", "").lower() == "subject":
            return (h.get("value") or "").strip()
    return "LINE_export"


def is_line_export_attachment(filename: str) -> bool:
    low = filename.lower()
    return low.endswith(".txt") or low.endswith(".text")


def save_attachment_to_inbox(
    service,
    message_id: str,
    part: dict,
    inbox: Path,
    *,
    subject: str,
    date_prefix: str,
    dry_run: bool,
) -> str | None:
    fname = part.get("filename") or "line_export.txt"
    if not is_line_export_attachment(fname):
        return None
    safe_subj = sanitize_filename(subject)[:60]
    dest_name = f"{safe_subj}_{date_prefix}_{sanitize_filename(fname)}"
    dest = unique_dest(inbox, dest_name)
    if dry_run:
        return dest.name
    att = (
        service.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=part["attachmentId"])
        .execute()
    )
    data = att.get("data", "").replace("-", "+").replace("_", "/")
    buf = base64.b64decode(data)
    inbox.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(buf)
    return dest.name


def fetch_line_exports_from_gmail(
    *,
    inbox_dir: Path | None = None,
    routes_path: Path | None = None,
    state_path: Path | None = None,
    days: int | None = None,
    dry_run: bool = False,
    max_messages: int = 50,
) -> GmailFetchStats:
    inbox = (inbox_dir or default_inbox_dir()).expanduser().resolve()
    routes_p = routes_path or default_routes_path()
    cfg = load_gmail_config(routes_p)
    if cfg.get("enabled") is False:
        stats = GmailFetchStats()
        stats.messages.append("gmail.enabled=false のためスキップ")
        return stats

    day_window = int(days if days is not None else cfg.get("days") or 365)
    query = build_query(cfg, day_window)
    sp = state_path or Path(
        os.environ.get("LINE_EXPORT_GMAIL_STATE_PATH", str(DEFAULT_STATE))
    )
    state = load_state(sp)
    stats = GmailFetchStats(query=query)
    expected = expected_gmail_account(cfg)

    token_path = resolve_gmail_token_path(cfg)
    if token_path is None:
        stats.messages.append(
            f"token がありません: {cfg.get('token_file') or DEFAULT_GMAIL_TOKEN}"
        )
        return stats

    try:
        service, email_addr = build_service_for_token(token_path)
    except Exception as e:
        stats.messages.append(f"Gmail認証失敗 ({token_path.name}): {e}")
        return stats

    stats.account = email_addr
    if expected and email_addr.lower() != expected.lower():
        stats.messages.append(
            f"警告: 期待アカウント {expected} ≠ 実際 {email_addr}"
        )

    res = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_messages)
        .execute()
    )
    items = res.get("messages") or []
    if not items:
        stats.messages.append(
            f"該当メールなし（{email_addr} / 直近{day_window}日）"
        )

    for item in items:
        mid = item.get("id")
        if not mid:
            continue
        if mid in state.get("messages", {}) and not dry_run:
            stats.skipped += 1
            continue
        stats.scanned += 1
        msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
        payload = msg.get("payload") or {}
        headers = payload.get("headers") or []
        subject = subject_from_headers(headers)
        date_prefix = message_date_jst(headers)
        parts = collect_attachment_parts(payload)
        saved_names: list[str] = []
        for part in parts:
            name = save_attachment_to_inbox(
                service,
                mid,
                part,
                inbox,
                subject=subject,
                date_prefix=date_prefix,
                dry_run=dry_run,
            )
            if name:
                saved_names.append(name)
                stats.saved += 1
                stats.files.append(name)

        if saved_names:
            stats.messages.append(
                f"保存: {email_addr} / {subject[:40]} → {', '.join(saved_names)}"
            )
            if not dry_run:
                state.setdefault("messages", {})[mid] = {
                    "files": saved_names,
                    "subject": subject,
                    "account": email_addr,
                    "ts": datetime.now().isoformat(timespec="seconds"),
                }
                save_state(sp, state)
        elif mid not in state.get("messages", {}):
            stats.skipped += 1

    return stats


def render_routine_block(stats: GmailFetchStats) -> str:
    acct = stats.account or DEFAULT_GMAIL_ACCOUNT
    lines = [
        "---",
        f"📎 {ROUTINE_MARKER}",
        f"- アカウント: {acct}",
        f"- Gmail スキャン: {stats.scanned}件（inbox 保存 {stats.saved} / スキップ {stats.skipped}）",
    ]
    if stats.files:
        lines.append(f"- 保存ファイル: {', '.join(stats.files[:5])}" + (" …" if len(stats.files) > 5 else ""))
    else:
        lines.append("- 保存ファイル: なし")
    lines.append("---")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gmail の LINE エクスポート添付 → inbox")
    parser.add_argument("--inbox-dir", type=Path, default=None)
    parser.add_argument("--routes-yaml", type=Path, default=None)
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-messages", type=int, default=50)
    args = parser.parse_args()

    stats = fetch_line_exports_from_gmail(
        inbox_dir=args.inbox_dir,
        routes_path=args.routes_yaml,
        days=args.days,
        dry_run=bool(args.dry_run),
        max_messages=max(1, args.max_messages),
    )
    for msg in stats.messages:
        print(msg, file=sys.stderr)
    print(render_routine_block(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
