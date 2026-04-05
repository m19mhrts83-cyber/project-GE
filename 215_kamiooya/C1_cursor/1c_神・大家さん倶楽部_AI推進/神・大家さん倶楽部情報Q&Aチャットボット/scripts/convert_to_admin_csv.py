#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WeStudy トピック別スクレイプCSV → WeStudy 管理者CSVエクスポート形式に正規化する。

入力（いずれかの列セット）:
  - 新: topic_title, topic_url, comment_id, comment_url, profile_url, parent_comment_id,
        author, time_text, time_iso, body  （westudy_forum_all.py）
  - 旧: topic_title, topic_url, comment_id, comment_url, user, profile_url, date, content

出力ヘッダ（管理者CSVと同一）:
  コメントID,投稿日時,投稿者名,投稿者メール,コメント内容,親コメントID,IP アドレス,ユーザーエージェント
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ADMIN_FIELDNAMES = [
    "コメントID",
    "投稿日時",
    "投稿者名",
    "投稿者メール",
    "コメント内容",
    "親コメントID",
    "IP アドレス",
    "ユーザーエージェント",
]

SKIP_NAME_PARTS = ("merged", "manifest", "topics_manifest", "summary", "failures")


def should_skip_csv_path(path: str) -> bool:
    lower = os.path.basename(path).lower()
    return any(p in lower for p in SKIP_NAME_PARTS)


def get_cell(row: dict, *keys: str) -> str:
    for k in keys:
        if k in row and row[k] is not None:
            v = str(row[k]).strip()
            if v:
                return v
    return ""


def normalize_comment_id(raw: str) -> str:
    s = (raw or "").strip().strip('"')
    if s.startswith("comment-"):
        s = s[8:].strip()
    return s


def normalize_parent_id(raw: str) -> str:
    s = (raw or "").strip().strip('"')
    if s.startswith("comment-"):
        s = s[8:].strip()
    return s


_JP_DT = re.compile(
    r"^(\d{4})年(\d{1,2})月(\d{1,2})日\s*(?:(\d{1,2})時(\d{1,2})分)?"
)


def format_posted_at(row: dict) -> str:
    """管理者CSVの「投稿日時」形式 YYYY-MM-DD HH:MM:SS に寄せる。"""
    time_iso = get_cell(row, "time_iso", "timeISO")
    time_text = get_cell(row, "time_text", "timeText")
    date_legacy = get_cell(row, "date", "投稿日時", "posted_at", "postedAt")
    for candidate in (time_iso, date_legacy, time_text):
        if not candidate:
            continue
        s = candidate.strip()
        if not s:
            continue
        # ISO 8601
        try:
            iso = s.replace("Z", "+00:00")
            if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", s):
                return s[:19]
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pass
        m = _JP_DT.match(s)
        if m:
            y, mo, d, h, mi = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            hh = int(h) if h else 0
            mm = int(mi) if mi else 0
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d} {hh:02d}:{mm:02d}:00"
        if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", s):
            return s[:19]
    return ""


def row_to_admin(row: dict) -> dict | None:
    cid = normalize_comment_id(
        get_cell(row, "コメントID", "comment_id", "commentId")
    )
    body = get_cell(row, "コメント内容", "content", "body")
    if not cid and not body:
        return None
    if not cid:
        return None

    parent_raw = get_cell(row, "親コメントID", "parent_comment_id", "parentCommentId")
    parent = normalize_parent_id(parent_raw) if parent_raw else ""

    return {
        "コメントID": cid,
        "投稿日時": format_posted_at(row),
        "投稿者名": get_cell(row, "投稿者名", "author", "user", "author_name", "authorName"),
        "投稿者メール": get_cell(row, "投稿者メール", "author_email", "authorEmail", "メール"),
        "コメント内容": body,
        "親コメントID": parent,
        "IP アドレス": get_cell(row, "IP アドレス", "IPアドレス", "ip_address", "ipAddress", "IP"),
        "ユーザーエージェント": get_cell(
            row, "ユーザーエージェント", "user_agent", "userAgent", "UA"
        ),
    }


def list_topic_csvs(input_dir: str) -> list[str]:
    pattern = os.path.join(input_dir, "**", "*.csv")
    files = sorted(glob.glob(pattern, recursive=True))
    return [f for f in files if not should_skip_csv_path(f)]


def collect_admin_rows(input_dir: str, verbose: bool) -> tuple[list[dict], int]:
    files = list_topic_csvs(input_dir)
    if not files:
        return [], 0

    by_id: dict[str, dict] = {}
    rows_in = 0
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows_in += 1
                    admin = row_to_admin(row)
                    if not admin:
                        continue
                    cid = admin["コメントID"]
                    # 同一IDは後勝ち（再スクレイプで本文が更新された場合に寄せる）
                    by_id[cid] = admin
        except Exception as e:
            print(f"[WARN] skip {fp}: {e}", file=sys.stderr)
            continue

    if verbose:
        print(f"[convert] files={len(files)} rows_read={rows_in} unique_ids={len(by_id)}")

    def sort_key(item: dict) -> tuple[str, int]:
        cid = item["コメントID"]
        try:
            return ("", int(cid))
        except ValueError:
            return (cid, 0)

    out = sorted(by_id.values(), key=sort_key)
    return out, rows_in


def main() -> int:
    ap = argparse.ArgumentParser(description="WeStudy スクレイプCSV → 管理者CSV形式")
    ap.add_argument(
        "--input-dir",
        required=True,
        help="トピック別CSVが入ったディレクトリ（再帰探索）",
    )
    ap.add_argument(
        "--output",
        "-o",
        required=True,
        help="出力CSVパス",
    )
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    input_dir = os.path.abspath(os.path.expanduser(args.input_dir))
    if not os.path.isdir(input_dir):
        print(f"入力ディレクトリがありません: {input_dir}", file=sys.stderr)
        return 2

    rows, rows_in = collect_admin_rows(input_dir, args.verbose)
    out_path = Path(args.output).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=ADMIN_FIELDNAMES,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(
        f"OK: {out_path} ({len(rows)} 行, 読込 {rows_in} 行, ヘッダ={ADMIN_FIELDNAMES[0]}...)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
