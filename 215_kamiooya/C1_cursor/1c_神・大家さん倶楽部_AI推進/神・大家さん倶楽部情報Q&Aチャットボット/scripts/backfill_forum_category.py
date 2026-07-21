#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""raw トピックCSV / scrape から comment_id → 分類を Supabase comments へバックフィル。

  python3 backfill_forum_category.py --dry-run
  python3 backfill_forum_category.py --raw-dir ../../exports/raw/20260405-170234
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
CHATBOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
from forum_category_map import enrich_comment_meta  # noqa: E402


def load_env() -> None:
    for p in (
        Path.home() / "git-repos" / ".env.jarvis_private",
        CHATBOT / "scripts" / ".env",
        Path.home()
        / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
        / "C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env",
    ):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def normalize_cid(raw: str) -> str:
    s = (raw or "").strip().strip('"')
    if s.startswith("comment-"):
        s = s[8:].strip()
    return s


def collect_from_raw_csvs(raw_dir: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for fp in raw_dir.rglob("*.csv"):
        try:
            with fp.open("r", encoding="utf-8-sig", newline="", errors="replace") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or "comment_id" not in reader.fieldnames:
                    continue
                for row in reader:
                    cid = normalize_cid(row.get("comment_id") or "")
                    if not cid:
                        continue
                    title = (row.get("topic_title") or "").strip()
                    url = (row.get("topic_url") or "").strip()
                    out[cid] = enrich_comment_meta(title, url)
        except Exception as e:
            print(f"[WARN] {fp}: {e}", file=sys.stderr)
    return out


def collect_from_scrape(scrape_dir: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for fp in sorted(scrape_dir.glob("done__*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        title = str(data.get("title") or "").strip()
        url = str(data.get("url") or "").strip()
        meta = enrich_comment_meta(title, url)
        rows = data.get("rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            cid = normalize_cid(
                str(row.get("comment_id") or row.get("commentId") or row.get("id") or "")
            )
            if cid:
                out[cid] = meta
    return out


def ensure_columns(client) -> None:
    """PostgREST では ALTER できないので、列が無い場合の案内のみ。"""
    try:
        client.table("comments").select("forum_category").limit(1).execute()
    except Exception as e:
        print(
            "forum_category 列が無い可能性があります。Supabase SQL Editor で次を実行してください:\n"
            "alter table public.comments add column if not exists source_system text;\n"
            "alter table public.comments add column if not exists source_kind text;\n"
            "alter table public.comments add column if not exists forum_category text;\n"
            "alter table public.comments add column if not exists topic_title text;\n"
            f"detail: {e}",
            file=sys.stderr,
        )
        raise


def main() -> int:
    load_env()
    default_raw = (
        Path.home()
        / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
        / "C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット"
        / "exports/raw/20260405-170234"
    )
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=str(default_raw))
    ap.add_argument("--scrape-dir", default=str(CHATBOT / "state" / "westudy_scrape"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--chunk", type=int, default=50)
    args = ap.parse_args()

    mapping: dict[str, dict[str, str]] = {}
    raw_dir = Path(args.raw_dir).expanduser()
    if raw_dir.is_dir():
        mapping.update(collect_from_raw_csvs(raw_dir))
        print(f"from raw csv: {len(mapping)}")
    scrape_dir = Path(args.scrape_dir).expanduser()
    if scrape_dir.is_dir():
        extra = collect_from_scrape(scrape_dir)
        mapping.update(extra)
        print(f"after scrape merge: {len(mapping)}")

    cats: dict[str, int] = {}
    for m in mapping.values():
        c = m["forum_category"]
        cats[c] = cats.get(c, 0) + 1
    for k in sorted(cats, key=lambda x: -cats[x])[:40]:
        print(f"  {k}: {cats[k]}")

    if args.dry_run:
        print("dry-run: no DB write")
        return 0

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or ""
    ).strip()
    if not url or not key:
        print("SUPABASE_URL / KEY が未設定です", file=sys.stderr)
        return 1

    from supabase import create_client

    client = create_client(url, key)
    ensure_columns(client)

    # 同じ meta ごとに comment_id を束ねて .in_() 更新（1件ずつより大幅に速い）
    by_key: dict[tuple[str, str, str, str], list[str]] = {}
    for cid, meta in mapping.items():
        key = (
            meta["source_system"],
            meta["source_kind"],
            meta["forum_category"],
            meta.get("topic_title") or "",
        )
        by_key.setdefault(key, []).append(cid)

    updated = 0
    failed = 0
    for (source_system, source_kind, forum_category, topic_title), cids in by_key.items():
        payload = {
            "source_system": source_system,
            "source_kind": source_kind,
            "forum_category": forum_category,
            "topic_title": topic_title or None,
        }
        for i in range(0, len(cids), args.chunk):
            batch = cids[i : i + args.chunk]
            try:
                client.table("comments").update(payload).in_("comment_id", batch).execute()
                updated += len(batch)
                print(f"  +{len(batch)} {forum_category} (total {updated})", flush=True)
            except Exception as e:
                failed += len(batch)
                if failed <= 20:
                    print(f"[ERR] batch {forum_category}: {e}", file=sys.stderr)
    print(f"backfill done: updated={updated} failed={failed} groups={len(by_key)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
