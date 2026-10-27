#!/usr/bin/env python3
"""誤記補正済みの字幕チャンクを、埋め込みとRaimoに反映する。既定はプレビュー、--apply で実行。

本文の補正自体は 2026-10-26 に Supabase 上で実施済み（元の本文は kc_typo_backup_20261026）。
このスクリプトは補正したチャンクだけを対象にする:
  --reembed      補正後の本文で埋め込みを作り直す（Gemini、1,229件程度）
  --mirror-raimo 補正があった動画だけ、Raimo側のチャンクを入れ替える
  --course NAME  指定コースは、現在の補正表との差分を抽出して本文も更新する（複数指定可）。
                 --apply 前にローカル JSON バックアップを必ず作る。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from embed_to_supabase import load_env, get_client, batch_embed_texts
from mirror_knowledge_to_raimo import post_json
from transcript_corrections import fix_text, load_rules

BACKUP_TABLE = "kc_typo_backup_20261026"
CHUNK_COLS = "id,chunk_key,start_sec,end_sec,speaker,content,search_text"
SOURCE_COLS = "id,source_key,title,meta_json"


def fetch_targets(client) -> dict[int, list[dict]]:
    """補正したチャンクを動画ごとに返す。バックアップ表の id だけを読み、通信量を抑える。"""
    ids: list[int] = []
    while True:
        # PostgREST は1回1,000行までなので、ページを分けて全件読む
        page = client.table(BACKUP_TABLE).select("chunk_id").order("chunk_id").range(len(ids), len(ids) + 999).execute().data
        ids += [r["chunk_id"] for r in page]
        if len(page) < 1000:
            break
    chunks: list[dict] = []
    for i in range(0, len(ids), 200):
        chunks += client.table("knowledge_chunks").select(CHUNK_COLS + ",source_id").in_("id", ids[i:i+200]).execute().data
    by_source: dict[int, list[dict]] = {}
    for ch in chunks:
        by_source.setdefault(ch["source_id"], []).append(ch)
    return by_source


def fetch_course_targets(client, courses: list[str]) -> tuple[dict[int, dict], dict[int, list[dict]]]:
    """指定コースの全チャンクを取得し、補正表で本文が変わる行だけ返す。"""
    sources: dict[int, dict] = {}
    offset = 0
    while True:
        page = (
            client.table("knowledge_sources")
            .select(SOURCE_COLS)
            .eq("content_channel", "seminar_video")
            .order("id")
            .range(offset, offset + 999)
            .execute()
            .data
        )
        for row in page:
            meta = row.get("meta_json") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}
            if meta.get("course") in courses:
                sources[row["id"]] = {**row, "meta_json": meta}
        if len(page) < 1000:
            break
        offset += len(page)

    changed: dict[int, list[dict]] = {}
    for source_id in sorted(sources):
        rows: list[dict] = []
        offset = 0
        while True:
            page = (
                client.table("knowledge_chunks")
                .select(CHUNK_COLS + ",source_id,content_hash")
                .eq("source_id", source_id)
                .order("id")
                .range(offset, offset + 999)
                .execute()
                .data
            )
            rows += page
            if len(page) < 1000:
                break
            offset += len(page)
        for row in rows:
            fixed = fix_text(row.get("content") or "")
            if fixed != (row.get("content") or ""):
                row["fixed_content"] = fixed
                changed.setdefault(source_id, []).append(row)
    return sources, changed


def write_local_backup(sources: dict[int, dict], by_source: dict[int, list[dict]], backup_dir: Path) -> Path:
    """更新前本文をローカルだけに保存する。秘密値は含めない。"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = backup_dir / f"kamiooya_transcript_typo_backup_{stamp}.json"
    payload = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "rules": len(load_rules()),
        "sources": [
            {
                "source_id": source_id,
                "source_key": sources[source_id]["source_key"],
                "chunks": [
                    {k: row.get(k) for k in ("id", "chunk_key", "content", "search_text", "content_hash")}
                    for row in rows
                ],
            }
            for source_id, rows in sorted(by_source.items())
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def apply_course_text_updates(client, sources: dict[int, dict], by_source: dict[int, list[dict]], *, reembed_rows: bool) -> int:
    updated = 0
    for source_id, rows in sorted(by_source.items()):
        vectors = None
        if reembed_rows:
            # Gemini の batchEmbedContents は1回100件までなので、reembed() と同じ30件ずつに分ける
            vectors = []
            for i in range(0, len(rows), 30):
                vectors += batch_embed_texts([row["fixed_content"] for row in rows[i:i+30]])
        for index, row in enumerate(rows):
            fixed = row["fixed_content"]
            patch = {
                "content": fixed,
                "search_text": fix_text(row.get("search_text") or row.get("content") or ""),
                "content_hash": hashlib.sha256(fixed.encode("utf-8")).hexdigest(),
            }
            if vectors is not None:
                patch["embedding"] = vectors[index]
            client.table("knowledge_chunks").update(patch, returning="minimal").eq("id", row["id"]).execute()
            updated += 1
        source = sources[source_id]
        meta = dict(source.get("meta_json") or {})
        meta["typo_fix"] = {
            "rules": len(load_rules()),
            "applied_at": datetime.now().date().isoformat(),
            "backup": "local_json",
        }
        client.table("knowledge_sources").update({"meta_json": meta}, returning="minimal").eq("id", source_id).execute()
    return updated


def reembed(client, chunks: list[dict]) -> int:
    for i in range(0, len(chunks), 30):
        batch = chunks[i:i+30]
        vectors = batch_embed_texts([c["content"] for c in batch])
        for ch, vector in zip(batch, vectors):
            client.table("knowledge_chunks").update({"embedding": vector}, returning="minimal").eq("id", ch["id"]).execute()
    return len(chunks)


def mirror_raimo(client, base: str, source_ids: list[int]) -> int:
    """Raimo には更新APIが無いため、動画単位で削除→全チャンク再登録する。"""
    sent = 0
    for sid in source_ids:
        key = client.table("knowledge_sources").select("source_key").eq("id", sid).execute().data[0]["source_key"]
        rows = client.table("knowledge_chunks").select(CHUNK_COLS).eq("source_id", sid).order("start_sec").execute().data
        status, body = post_json(base, "/admin/knowledge-chunks/delete-by-source", {"source_key": key})
        if not 200 <= status < 300:
            raise RuntimeError(f"Raimo delete HTTP {status}: {key} {body[:200]}")
        for r in rows:
            row = {k: r[k] for k in ("chunk_key", "start_sec", "end_sec", "speaker", "content", "search_text")}
            row["source_key"] = key
            status, body = post_json(base, "/admin/knowledge-chunks", row)
            if not 200 <= status < 300:
                raise RuntimeError(f"Raimo chunk HTTP {status}: {r['chunk_key']}（この動画は再実行で入れ替え直す）")
        sent += len(rows)
        print(json.dumps({"source": key, "raimo_chunks": len(rows)}, ensure_ascii=False), flush=True)
    return sent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reembed", action="store_true")
    ap.add_argument("--mirror-raimo", action="store_true")
    ap.add_argument("--course", action="append", default=[], help="現在の補正表との差分を更新するコース名（複数指定可）")
    ap.add_argument(
        "--backup-dir",
        type=Path,
        default=Path.home() / "git-repos" / ".jarvis_state" / "kamiooya_typo_backups",
        help="コース更新前のローカルJSON保存先",
    )
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    load_env()
    if os.environ.get("SUPABASE_URL", "").rstrip("/") != "https://mwubzgefkkjjbingrmqu.supabase.co":
        raise RuntimeError("接続先が kamiooya-qa ではありません。SUPABASE_URLを確認してください")
    client = get_client()
    sources: dict[int, dict] = {}
    if args.course:
        sources, by_source = fetch_course_targets(client, args.course)
    else:
        by_source = fetch_targets(client)
    chunks = [c for rows in by_source.values() for c in rows]
    print(json.dumps({
        "courses": args.course,
        "rules": len(load_rules()),
        "sources": len(by_source),
        "chunks": len(chunks),
        "apply": args.apply,
    }, ensure_ascii=False))
    if not args.apply:
        return 0
    if args.course:
        backup = write_local_backup(sources, by_source, args.backup_dir)
        print(json.dumps({"backup": str(backup)}, ensure_ascii=False))
        print(json.dumps({"updated": apply_course_text_updates(client, sources, by_source, reembed_rows=args.reembed)}, ensure_ascii=False))
    elif args.reembed:
        print(json.dumps({"reembedded": reembed(client, chunks)}, ensure_ascii=False))
    if args.mirror_raimo:
        base = (os.environ.get("RAIMO_APP_URL") or os.environ.get("LIMO_APP_URL") or "").rstrip("/")
        if not base:
            raise RuntimeError("RAIMO_APP_URL missing")
        print(json.dumps({"raimo_chunks": mirror_raimo(client, base, sorted(by_source))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
