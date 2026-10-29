#!/usr/bin/env python3
"""inbox/notta に届いた Notta 書き出し（xlsx/srt）を週次で登録し、同じ動画の Whisper 版と差し替える。

方針（2026-10-28 松野さん）: 運営に Notta で起こしてもらった動画は、ローカルWhisper版を Notta版へ差し替える。
- 動画の特定: ファイル名に Vimeo ID（8〜11桁）を含める。または inbox の「対応表.csv」（file,vimeo_id）。
- 既存が local_whisper → Notta版を登録してから Whisper版チャンクを削除（Supabase・Raimo）。元本文は __whisper.md に残る。
- 既存が notta → 何もしない。vimeo_auto だけ → 二重登録を避けて「要確認」に回す（差し替えは未承認）。
- 既存なし → 対応表に slug と title があれば新規登録、無ければ「要確認」。
- 処理済みファイルは ledger（ファイルの sha256）に記録し、翌週は読まない。
既定はプレビュー。--apply で本番。Supabase は差分のみ（Free の通信量を抑える）。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

INBOX = Path.home() / ("Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/"
                       "1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/inbox/notta")
LEDGER = Path.home() / "git-repos/.jarvis_state/kamiooya_video_weekly/notta_ledger.json"
MAPPING = "対応表.csv"
SUFFIXES = {".xlsx", ".xlsm", ".srt"}


def load_mapping(inbox: Path) -> dict[str, dict]:
    path = inbox / MAPPING
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig") as f:
        return {(r.get("file") or "").strip(): r for r in csv.DictReader(f) if (r.get("file") or "").strip()}


def match_video_id(name: str, mapping: dict[str, dict]) -> str | None:
    row = mapping.get(name)
    if row and (row.get("vimeo_id") or "").strip().isdigit():
        return row["vimeo_id"].strip()
    ids = re.findall(r"(?<!\d)(\d{8,11})(?!\d)", Path(name).stem)
    return ids[0] if len(ids) == 1 else None


def provider(source: dict) -> str:
    if source["source_key"].startswith("notta:"):
        return "notta"
    return (source.get("meta_json") or {}).get("transcript_provider") or "vimeo_auto"


def plan(existing: list[dict], mapping_row: dict | None) -> tuple[str, list[dict]]:
    """('skip'|'replace'|'new'|'hold', 差し替える Whisper 版)"""
    kinds = {provider(s) for s in existing}
    if "notta" in kinds:
        return "skip", []
    whisper = [s for s in existing if provider(s) == "local_whisper"]
    if whisper and kinds == {"local_whisper"}:
        return "replace", whisper
    if existing:
        return "hold", []
    if mapping_row and (mapping_row.get("slug") or "").strip() and (mapping_row.get("title") or "").strip():
        return "new", []
    return "hold", []


def build_notta(path: Path, vid: str, digest: str, base: dict, cues, chunk_cues, fix_text) -> tuple[dict, list[dict]]:
    slug = base["slug"]
    key = f"notta:westudy:{slug}:vimeo:{vid}"
    meta = {"transcript_provider": "notta", "provisional": False, "course": base.get("course") or "",
            "lesson_slug": slug, "lesson_url": f"https://westudy.co.jp/lesson/{slug}",
            "origin_filename": path.name, "file_sha256": digest,
            "received_at": datetime.now(timezone.utc).astimezone().date().isoformat(),
            "replaces": base.get("replaces") or [], "correction_rules": "kamiooya_transcript_corrections.tsv"}
    source = {"source_key": key, "source_kind": "video", "content_channel": "seminar_video",
              "title": base["title"], "video_id": vid, "video_url": f"https://vimeo.com/{vid}",
              "origin_path": str(path), "ingest_status": "ready", "meta_json": meta}
    chunks = []
    for row in chunk_cues(cues, max_sec=90, max_chars=1000):
        text = fix_text(row["content"])
        h = hashlib.sha256(text.encode()).hexdigest()
        chunks.append({**row, "content": text, "search_text": text, "content_hash": h,
                       "chunk_key": f"{key}:{row['start_sec']}:{h[:16]}"})
    return source, chunks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inbox", type=Path, default=INBOX)
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--report", type=Path, help="結果 JSON の出力先")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from embed_to_supabase import load_env, get_client, batch_embed_texts
    from import_vimeo_transcripts import sync_raimo
    from mirror_knowledge_to_raimo import post_json
    from notta_to_knowledge import chunk_cues, parse_input
    from transcript_corrections import fix_text

    load_env()
    if os.environ.get("SUPABASE_URL", "").rstrip("/") != "https://mwubzgefkkjjbingrmqu.supabase.co":
        raise RuntimeError("kamiooya-qa以外への接続を拒否")
    client = get_client()
    base_url = os.environ.get("RAIMO_APP_URL") or os.environ.get("LIMO_APP_URL") or ""
    if args.apply and not base_url:
        raise RuntimeError("RAIMO_APP_URL missing")
    ledger = json.loads(args.ledger.read_text(encoding="utf-8")) if args.ledger.exists() else {}
    mapping = load_mapping(args.inbox)
    cache: dict = {}
    results = []
    files = sorted(p for p in args.inbox.rglob("*") if p.suffix.lower() in SUFFIXES) if args.inbox.is_dir() else []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in ledger:
            continue
        res = {"file": str(path.relative_to(args.inbox)), "file_sha256": digest}
        vid = match_video_id(path.name, mapping)
        if not vid:
            results.append({**res, "action": "hold", "why": "Vimeo IDが分からない（ファイル名か対応表.csvに書いてください）"})
            continue
        cues, warnings = parse_input(path)
        if warnings or not cues or cues[-1].start_sec == 0:
            results.append({**res, "video_id": vid, "action": "hold", "why": f"時刻付きの字幕を読めない: {warnings[:2]}"})
            continue
        existing = (client.table("knowledge_sources").select("id,source_key,title,meta_json")
                    .eq("video_id", vid).execute().data)
        row = mapping.get(path.name)
        action, whisper = plan(existing, row)
        res.update(video_id=vid, action=action)
        if action in ("skip", "hold"):
            res["why"] = "Notta版は登録済み" if action == "skip" else "Vimeo字幕版あり、または動画情報不足（差し替えは未承認）"
            results.append(res)
            if action == "skip" and args.apply:
                ledger[digest] = res
            continue
        if whisper:
            meta = whisper[0].get("meta_json") or {}
            title = re.sub(r"（動画\d+）$", "", whisper[0]["title"])
            base = {"slug": meta.get("lesson_slug") or whisper[0]["source_key"].split(":")[1], "title": title,
                    "course": meta.get("course"), "replaces": [s["source_key"] for s in whisper]}
        else:
            base = {"slug": row["slug"].strip(), "title": row["title"].strip(), "course": (row.get("course") or "").strip()}
        source, chunks = build_notta(path, vid, digest, base, cues, chunk_cues, fix_text)
        res.update(source_key=source["source_key"], chunks=len(chunks), replaces=base.get("replaces") or [])
        if args.apply:
            sid = client.table("knowledge_sources").upsert(source, on_conflict="source_key").execute().data[0]["id"]
            for i in range(0, len(chunks), 30):  # Gemini 埋め込みは1回100件上限。30件ずつ
                batch = chunks[i:i + 30]
                vectors = batch_embed_texts([r["content"] for r in batch])
                client.table("knowledge_chunks").upsert([{**r, "source_id": sid, "embedding": v} for r, v in zip(batch, vectors)],
                                                        on_conflict="chunk_key").execute()
            sync_raimo(base_url, source, chunks, cache)
            # Notta版が入ってから Whisper版を外す（検索に穴を空けない）
            for s in whisper:
                client.table("knowledge_chunks").delete().eq("source_id", s["id"]).execute()
                meta = {**(s.get("meta_json") or {}), "replaced_by": source["source_key"],
                        "replaced_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                client.table("knowledge_sources").update({"meta_json": meta}).eq("id", s["id"]).execute()
                status, body = post_json(base_url, "/admin/knowledge-chunks/delete-by-source", {"source_key": s["source_key"]})
                if not 200 <= status < 300:
                    raise RuntimeError(f"Raimo delete HTTP {status}: {s['source_key']} {body[:200]}")
            ledger[digest] = res
            args.ledger.parent.mkdir(parents=True, exist_ok=True)
            args.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append(res)
        print(json.dumps(res, ensure_ascii=False), flush=True)
    if args.apply:
        args.ledger.parent.mkdir(parents=True, exist_ok=True)
        args.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"files": len(results), "replaced": sum(r["action"] == "replace" for r in results),
               "new": sum(r["action"] == "new" for r in results), "hold": [r for r in results if r["action"] == "hold"],
               "applied": args.apply}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({**summary, "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
