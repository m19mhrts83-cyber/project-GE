#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supabase public.comments へ WeStudy 管理者形式 CSV を upsert する。

必須環境変数:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY（必須・推奨）
    未設定時は SUPABASE_ANON_KEY をフォールバックするが、
    RLS 有効化後は anon では書けないため service_role を使うこと

使い方:
  python3 upload_csv_to_supabase.py --csv exports/delta_*.csv
  python3 upload_csv_to_supabase.py --bootstrap --csv exports/full_*.csv
  python3 upload_csv_to_supabase.py --dry-run --csv exports/delta_*.csv

終了時に次の行を stdout へ出力（ログパース用）:
  Supabase取込完了: upserted=N skipped=M failed=K mode=delta|bootstrap
  emb未付与: N   （--since 指定時のみ。新規 upsert 分のうち embedding が null の件数）
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from forum_category_map import enrich_comment_meta
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from forum_category_map import enrich_comment_meta

CSV_CELL_ALIASES: dict[str, tuple[str, ...]] = {
    "comment_id": ("comment_id", "commentId", "コメントID", "コメントid"),
    "posted_at": ("posted_at", "postedAt", "日時", "投稿日時", "投稿日"),
    "author_name": ("author_name", "authorName", "投稿者名", "投稿者", "author"),
    "author_email": ("author_email", "authorEmail", "投稿者メール", "メール"),
    "content": ("content", "本文", "Content", "コメント内容", "comment_body"),
    "parent_comment_id": (
        "parent_comment_id",
        "parentCommentId",
        "親コメントID",
        "親コメントid",
    ),
    "ip_address": ("ip_address", "ipAddress", "IPアドレス", "IP アドレス", "IP"),
    "user_agent": ("user_agent", "userAgent", "ユーザーエージェント", "UA"),
    "source_type": ("source_type", "ソース", "sourceType", "データソース"),
    "source_system": ("source_system", "ソース系統", "sourceSystem"),
    "source_kind": ("source_kind", "ソース種別", "sourceKind"),
    "forum_category": ("forum_category", "分類", "forumCategory", "カテゴリ"),
    "topic_title": ("topic_title", "板タイトル", "topicTitle", "トピック名"),
    "course_tab": ("course_tab", "コースタブ"),
    "section_name": ("section_name", "目次セクション"),
    "lesson_title": ("lesson_title", "レッスンタイトル"),
    "lesson_url": ("lesson_url", "レッスンURL"),
    "content_hash": ("content_hash", "コンテンツハッシュ"),
}


def csv_cell(row: dict[str, str], field: str) -> str:
    for key in CSV_CELL_ALIASES[field]:
        if key in row and row[key] is not None:
            val = str(row[key]).strip()
            if val:
                return val
    return ""


def normalize_posted_at(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", s):
        return s[:19].replace(" ", "T") + "+00:00"
    if re.match(r"^\d{4}-\d{2}-\d{2}T", s):
        return s
    return s


def parse_since(raw: str | None) -> datetime | None:
    """YYYY-MM-DD または ISO。日付のみは UTC 0:00。空なら None。"""
    s = (raw or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def posted_at_as_utc(value: str | None) -> datetime | None:
    s = (value or "").strip()
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", s):
        s = s[:19].replace(" ", "T") + "+00:00"
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        s = s + "T00:00:00+00:00"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def select_records_since(
    records: list[dict[str, Any]],
    since: datetime | None,
    *,
    bootstrap: bool,
) -> tuple[list[dict[str, Any]], int]:
    """posted_at >= since だけ残す。日時なし・解釈不能・since より前はスキップ。

    bootstrap（全件）では床を無視する。
    """
    if since is None or bootstrap:
        return records, 0
    kept: list[dict[str, Any]] = []
    skipped = 0
    for rec in records:
        posted = posted_at_as_utc(str(rec.get("posted_at") or ""))
        if posted is None or posted < since:
            skipped += 1
            continue
        kept.append(rec)
    return kept, skipped


def row_to_record(row: dict[str, str], row_index: int, import_batch_ts: int) -> dict[str, Any] | None:
    explicit_id = csv_cell(row, "comment_id")
    content = csv_cell(row, "content")
    if not explicit_id and not content:
        return None
    comment_id = explicit_id or f"csv-{import_batch_ts}-{row_index}"

    source_type = csv_cell(row, "source_type")
    if not source_type:
        if "コメントID" in row and "コメント内容" in row:
            source_type = "神大家コミュニティ"
        else:
            source_type = "WeStudy"

    posted_at = normalize_posted_at(csv_cell(row, "posted_at"))

    def opt(field: str) -> str | None:
        v = csv_cell(row, field)
        return v or None

    topic_title = opt("topic_title") or ""
    meta = enrich_comment_meta(topic_title, "")
    forum_category = opt("forum_category") or meta["forum_category"]
    source_system = opt("source_system") or meta["source_system"]
    source_kind = opt("source_kind") or meta["source_kind"]

    return {
        "comment_id": comment_id,
        "source_type": source_type,
        "source_system": source_system,
        "source_kind": source_kind,
        "forum_category": forum_category,
        "topic_title": topic_title or None,
        "posted_at": posted_at,
        "author_name": opt("author_name"),
        "author_email": opt("author_email"),
        "content": content,
        "parent_comment_id": opt("parent_comment_id"),
        "ip_address": opt("ip_address"),
        "user_agent": opt("user_agent"),
        "course_tab": opt("course_tab"),
        "section_name": opt("section_name"),
        "lesson_title": opt("lesson_title"),
        "lesson_url": opt("lesson_url"),
        "content_hash": opt("content_hash"),
    }


def read_csv_records(csv_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    import_batch_ts = int(time.time() * 1000)
    with csv_path.open("r", encoding="utf-8-sig", newline="", errors="replace") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError("CSV にヘッダ行がありません")
        for i, row in enumerate(reader):
            rec = row_to_record(row, i, import_batch_ts)
            if not rec or not rec.get("content"):
                continue
            cid = str(rec.get("comment_id") or "").strip()
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            records.append(rec)
    return records


def get_supabase_client():
    try:
        from supabase import create_client
    except ImportError as e:  # pragma: no cover
        print(
            "supabase パッケージが必要です: pip install supabase\n"
            f"detail: {e}",
            file=sys.stderr,
        )
        raise SystemExit(2) from e
    url = os.environ.get("SUPABASE_URL", "").strip()
    if not url:
        raise RuntimeError("環境変数 SUPABASE_URL が未設定です")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_ANON_KEY", "").strip()
    )
    if not key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY（推奨）または SUPABASE_ANON_KEY を設定してください"
        )
    return create_client(url, key)


def count_missing_embeddings(client, comment_ids: list[str]) -> int:
    """upsert 済み comment_id のうち embedding が null の件数。"""
    ids = [cid for cid in comment_ids if cid]
    total = 0
    for start in range(0, len(ids), 80):
        chunk = ids[start : start + 80]
        res = (
            client.table("comments")
            .select("comment_id")
            .in_("comment_id", chunk)
            .is_("embedding", "null")
            .limit(len(chunk))
            .execute()
        )
        total += len(res.data or [])
    return total


def upsert_chunk(client: Client, chunk: list[dict[str, Any]], retries: int = 3) -> None:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            client.table("comments").upsert(chunk, on_conflict="comment_id").execute()
            return
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"chunk upsert failed after {retries} tries: {last_err}")


def upload_records(
    client,
    records: list[dict[str, Any]],
    *,
    chunk_size: int,
    dry_run: bool,
) -> tuple[int, int, int, list[str]]:
    if dry_run:
        print(f"[dry-run] rows={len(records)} chunk_size={chunk_size}")
        for rec in records[:3]:
            print(f"[dry-run] sample comment_id={rec.get('comment_id')}")
        return 0, 0, 0, []

    upserted = 0
    failed = 0
    ok_ids: list[str] = []
    for start in range(0, len(records), chunk_size):
        chunk = records[start : start + chunk_size]
        try:
            upsert_chunk(client, chunk)
            upserted += len(chunk)
            ok_ids.extend(
                str(rec.get("comment_id") or "")
                for rec in chunk
                if rec.get("comment_id")
            )
            print(f"  chunk ok: {start + 1}-{start + len(chunk)} / {len(records)}")
        except Exception as e:
            failed += len(chunk)
            print(f"  chunk NG: {start + 1}-{start + len(chunk)}: {e}", file=sys.stderr)
    skipped = 0
    return upserted, skipped, failed, ok_ids


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WeStudy CSV を Supabase comments へ upsert")
    p.add_argument("--csv", required=True, help="取込 CSV パス（delta_*.csv または full_*.csv）")
    p.add_argument(
        "--bootstrap",
        action="store_true",
        help="全件ブートストラップ（full_*.csv 想定。delta でも upsert 可）",
    )
    p.add_argument("--dry-run", action="store_true", help="接続・マッピングのみ確認")
    p.add_argument("--chunk-size", type=int, default=300, help="1回の upsert 件数（既定 300）")
    p.add_argument(
        "--since",
        default="",
        help="この日付（UTC・含む）より前、または投稿日時なしは取り込まない。例: 2026-09-27。--bootstrap では無視",
    )
    return p.parse_args()


def report_missing_embeddings(client, comment_ids: list[str], *, since_active: bool) -> None:
    """週次ログ用。--since のときだけ `emb未付与: N` を1行出す。"""
    if not since_active:
        return
    if not comment_ids:
        print("emb未付与: 0")
        return
    try:
        missing = count_missing_embeddings(client, comment_ids)
    except Exception as e:
        print(f"emb未付与の照会に失敗: {e}", file=sys.stderr)
        return
    print(f"emb未付与: {missing}")


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.is_file():
        print(f"CSV が見つかりません: {csv_path}", file=sys.stderr)
        return 2

    try:
        since = parse_since(args.since)
    except ValueError:
        print(f"--since を解釈できません: {args.since}", file=sys.stderr)
        return 2

    mode = "bootstrap" if args.bootstrap else "delta"
    records = read_csv_records(csv_path)
    records, skipped_since = select_records_since(
        records, since, bootstrap=bool(args.bootstrap)
    )
    since_active = since is not None and not args.bootstrap
    if skipped_since:
        print(f"since 床でスキップ: {skipped_since} 件（posted_at < {since.isoformat()} または日時なし）")
    print(f"==> Supabase CSV取込 mode={mode} file={csv_path} rows={len(records)}")

    if len(records) == 0:
        print(
            f"Supabase取込完了: upserted=0 skipped={skipped_since} failed=0 mode={mode} (empty)"
        )
        if since_active:
            print("emb未付与: 0")
        return 0

    if args.dry_run:
        upload_records(None, records, chunk_size=args.chunk_size, dry_run=True)
        print(
            f"Supabase取込完了: upserted=0 skipped={skipped_since} failed=0 mode={mode} dry_run=1"
        )
        return 0

    client = get_supabase_client()
    upserted, skipped_upload, failed, ok_ids = upload_records(
        client, records, chunk_size=max(1, args.chunk_size), dry_run=False
    )
    skipped = skipped_since + skipped_upload
    print(
        f"Supabase取込完了: upserted={upserted} skipped={skipped} failed={failed} mode={mode}"
    )
    report_missing_embeddings(client, ok_ids, since_active=since_active)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
