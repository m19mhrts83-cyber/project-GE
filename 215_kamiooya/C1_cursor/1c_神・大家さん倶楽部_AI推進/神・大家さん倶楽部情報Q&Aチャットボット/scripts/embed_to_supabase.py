#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supabase comments / knowledge_chunks の embedding 欄を Gemini で埋める。

必須環境変数:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY（推奨）
  GEMINI_API_KEY

使い方:
  python3 embed_to_supabase.py --table knowledge_chunks
  python3 embed_to_supabase.py --table comments --batch-size 50
  python3 embed_to_supabase.py --table comments --limit 200 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from supabase import Client, create_client
except ImportError as e:  # pragma: no cover
    print(
        "supabase パッケージが必要です: pip install supabase\n"
        f"detail: {e}",
        file=sys.stderr,
    )
    raise SystemExit(2)

# text-embedding-004 は現行キーでは不可。gemini-embedding-001 + 768次元で schema と揃える。
GEMINI_EMBED_MODEL = "gemini-embedding-001"
GEMINI_EMBED_DIM = 768
GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_EMBED_MODEL}:batchEmbedContents"
)
TABLES = ("comments", "knowledge_chunks")


def load_env() -> None:
    roots = [
        Path.home() / "git-repos" / ".env.jarvis_private",
        Path(__file__).resolve().parent / ".env",
    ]
    for p in roots:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"環境変数 {name} が未設定です")
    return value


def get_client() -> Client:
    url = require_env("SUPABASE_URL")
    key = (
        (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        or (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    )
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY または SUPABASE_ANON_KEY を設定してください")
    return create_client(url, key)


def fetch_pending_rows(
    client: Client, table: str, batch_size: int, cursor_id: int | None
) -> list[dict[str, Any]]:
    if table == "comments":
        select_cols = "id,comment_id,content"
    else:
        select_cols = "id,chunk_key,content"
    query = (
        client.table(table)
        .select(select_cols)
        .is_("embedding", "null")
        .order("id")
        .limit(batch_size)
    )
    if cursor_id is not None:
        query = query.gt("id", cursor_id)
    result = query.execute()
    return list(result.data or [])


def batch_embed_texts(texts: list[str]) -> list[list[float]]:
    api_key = require_env("GEMINI_API_KEY")
    payload = {
        "requests": [
            {
                "model": f"models/{GEMINI_EMBED_MODEL}",
                "content": {"parts": [{"text": text}]},
                "taskType": "RETRIEVAL_DOCUMENT",
                "outputDimensionality": GEMINI_EMBED_DIM,
            }
            for text in texts
        ]
    }
    req = urllib.request.Request(
        GEMINI_EMBED_URL + "?key=" + urllib.parse.quote(api_key),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Gemini embedding failed: HTTP {e.code} {detail[:240]}") from e
    json_data = json.loads(raw)
    embeddings = json_data.get("embeddings") or []
    values: list[list[float]] = []
    for item in embeddings:
        vector = ((item or {}).get("values")) or []
        if not vector:
            raise RuntimeError("Gemini embedding response is empty")
        values.append(vector)
    if len(values) != len(texts):
        raise RuntimeError(
            f"Gemini embedding count mismatch: expected={len(texts)} actual={len(values)}"
        )
    return values


def update_embeddings(client: Client, table: str, rows: list[dict[str, Any]], dry_run: bool) -> int:
    texts = [str((row.get("content") or "")).strip() for row in rows]
    if dry_run:
        print(
            f"[dry-run] table={table} rows={len(rows)} sample_id={rows[0].get('id') if rows else '—'}"
        )
        return 0
    embeddings = batch_embed_texts(texts)
    updated = 0
    for row, embedding in zip(rows, embeddings):
        last_err: Exception | None = None
        for attempt in range(1, 6):
            try:
                client.table(table).update({"embedding": embedding}).eq("id", row["id"]).execute()
                updated += 1
                last_err = None
                break
            except Exception as e:  # network blips on long runs
                last_err = e
                wait_s = min(30, 2 ** attempt)
                print(
                    f"warn: update id={row.get('id')} attempt={attempt}/5 err={type(e).__name__}: {e}; sleep {wait_s}s",
                    flush=True,
                )
                time.sleep(wait_s)
                client = get_client()
        if last_err is not None:
            raise last_err
    return updated


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Supabase の embedding 欄を Gemini で更新")
    p.add_argument(
        "--table",
        action="append",
        choices=TABLES,
        required=True,
        help="対象テーブル（複数指定可）",
    )
    p.add_argument("--batch-size", type=int, default=50, help="1回の埋め込み件数（既定 50）")
    p.add_argument("--limit", type=int, default=0, help="総件数上限（0 は無制限）")
    p.add_argument("--dry-run", action="store_true", help="対象件数だけ確認して更新しない")
    p.add_argument("--sleep-ms", type=int, default=250, help="バッチ間待機ミリ秒")
    return p.parse_args()


def run_table(
    client: Client, table: str, *, batch_size: int, limit: int, dry_run: bool, sleep_ms: int
) -> tuple[int, int]:
    updated = 0
    scanned = 0
    cursor_id: int | None = None
    while True:
        remaining = limit - updated if limit > 0 else batch_size
        fetch_size = min(batch_size, remaining) if limit > 0 else batch_size
        if fetch_size <= 0:
            break
        rows = None
        for attempt in range(1, 6):
            try:
                rows = fetch_pending_rows(client, table, fetch_size, cursor_id)
                break
            except Exception as e:
                wait_s = min(30, 2 ** attempt)
                print(
                    f"warn: fetch attempt={attempt}/5 err={type(e).__name__}: {e}; sleep {wait_s}s",
                    flush=True,
                )
                time.sleep(wait_s)
                client = get_client()
        if rows is None:
            raise RuntimeError("fetch_pending_rows failed after retries")
        if not rows:
            break
        scanned += len(rows)
        cursor_id = int(rows[-1]["id"])
        done = update_embeddings(client, table, rows, dry_run)
        # refresh client periodically to avoid long-lived HTTP/2 disconnects
        if scanned % 500 == 0:
            client = get_client()
        updated += done
        print(
            f"embedding {table}: batch={len(rows)} updated={updated} scanned={scanned} last_id={cursor_id}",
            flush=True,
        )
        if dry_run:
            break
        time.sleep(max(0, sleep_ms) / 1000)
    return updated, scanned


def main() -> int:
    load_env()
    args = parse_args()
    client = get_client()
    overall_updated = 0
    overall_scanned = 0
    for table in args.table:
        updated, scanned = run_table(
            client,
            table,
            batch_size=max(1, min(args.batch_size, 100)),
            limit=max(0, args.limit),
            dry_run=args.dry_run,
            sleep_ms=args.sleep_ms,
        )
        overall_updated += updated
        overall_scanned += scanned
        print(
            f"embedding done: table={table} updated={updated} scanned={scanned} dry_run={int(args.dry_run)}"
        )
    print(
        f"embedding total: updated={overall_updated} scanned={overall_scanned} dry_run={int(args.dry_run)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
