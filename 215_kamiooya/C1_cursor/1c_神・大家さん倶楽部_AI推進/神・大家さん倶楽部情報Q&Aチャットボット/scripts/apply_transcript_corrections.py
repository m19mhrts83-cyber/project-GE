#!/usr/bin/env python3
"""誤記補正済みの字幕チャンクを、埋め込みとRaimoに反映する。既定はプレビュー、--apply で実行。

本文の補正自体は 2026-10-26 に Supabase 上で実施済み（元の本文は kc_typo_backup_20261026）。
このスクリプトは補正したチャンクだけを対象にする:
  --reembed      補正後の本文で埋め込みを作り直す（Gemini、1,229件程度）
  --mirror-raimo 補正があった動画だけ、Raimo側のチャンクを入れ替える
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from embed_to_supabase import load_env, get_client, batch_embed_texts
from mirror_knowledge_to_raimo import post_json

BACKUP_TABLE = "kc_typo_backup_20261026"
CHUNK_COLS = "id,chunk_key,start_sec,end_sec,speaker,content,search_text"


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
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    load_env()
    if os.environ.get("SUPABASE_URL", "").rstrip("/") != "https://mwubzgefkkjjbingrmqu.supabase.co":
        raise RuntimeError("接続先が kamiooya-qa ではありません。SUPABASE_URLを確認してください")
    client = get_client()
    by_source = fetch_targets(client)
    chunks = [c for rows in by_source.values() for c in rows]
    print(json.dumps({"sources": len(by_source), "chunks": len(chunks), "apply": args.apply}, ensure_ascii=False))
    if not args.apply:
        return 0
    if args.reembed:
        print(json.dumps({"reembedded": reembed(client, chunks)}, ensure_ascii=False))
    if args.mirror_raimo:
        base = (os.environ.get("RAIMO_APP_URL") or os.environ.get("LIMO_APP_URL") or "").rstrip("/")
        if not base:
            raise RuntimeError("RAIMO_APP_URL missing")
        print(json.dumps({"raimo_chunks": mirror_raimo(client, base, sorted(by_source))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
