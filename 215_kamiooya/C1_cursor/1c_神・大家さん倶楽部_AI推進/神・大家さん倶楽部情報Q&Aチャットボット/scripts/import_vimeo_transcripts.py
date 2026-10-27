#!/usr/bin/env python3
"""Vimeo字幕MD → Supabase → Raimo。既定はプレビュー、--apply で追加する。"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "config/kamiooya_kiso_transcripts.yaml").exists())
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "scripts"))

from embed_to_supabase import load_env, get_client, batch_embed_texts
from notta_to_knowledge import Cue, chunk_cues, parse_timestamp
from mirror_knowledge_to_raimo import get_json, post_json
from transcript_corrections import fix_text


def retry(operation):
    """一時的な通信切断だけを再試行。認証・データ不整合は即停止。"""
    for attempt in range(3):
        try:
            return operation()
        except Exception as error:
            transient = isinstance(error, (TimeoutError, ConnectionError)) or any(
                text in str(error).lower() for text in ('timed out', 'connection reset', 'disconnected', 'http 429', 'http 502', 'http 503', 'http 504')
            )
            if not transient or attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def parse_videos(text: str) -> list[tuple[str, list[Cue]]]:
    """動画ごとに時計を分離。説明文・字幕なしは文字起こしに混ぜない。"""
    videos: list[tuple[str, list[Cue]]] = []
    current: list[Cue] | None = None
    for line in text.splitlines():
        video = re.match(r"^## 動画 \d+: Vimeo (\d+)\b", line)
        if video:
            current = []
            videos.append((video[1], current))
            continue
        cue = re.match(r"^\[(\d+:\d{2}(?::\d{2})?)\]\s+(.+)$", line)
        if cue and current is not None:
            start = parse_timestamp(cue[1])
            if start is not None:
                current.append(Cue(start, None, None, cue[2].strip()))
    return [(vid, cues) for vid, cues in videos if cues]


def build_records(lesson: dict, text: str, origin: str, course: str) -> list[tuple[dict, list[dict]]]:
    records = []
    for video_id, cues in parse_videos(text):
        key = f"westudy:{lesson['slug']}:vimeo:{video_id}"
        source = {
            "source_key": key, "source_kind": "video", "content_channel": "seminar_video",
            # 取込経路は meta_json で管理し、利用者に見えるタイトルには出さない
            "title": f"{lesson.get('title') or lesson['slug']}（動画{video_id}）",
            "video_id": video_id, "video_url": f"https://vimeo.com/{video_id}",
            "origin_path": origin, "ingest_status": "ready",
            "meta_json": {"transcript_provider": "vimeo_auto", "provisional": True,
                          "course": course, "lesson_slug": lesson['slug'], "lesson_url": lesson.get('url'),
                          "content_sha256": hashlib.sha256(text.encode()).hexdigest()},
        }
        chunks = []
        for ch in chunk_cues(cues, max_sec=90, max_chars=1000):
            # chunk_key は補正前の本文から作る（補正済みの既存チャンクと同じキーになり、重複登録しない）
            digest = hashlib.sha256(ch['content'].encode()).hexdigest()
            fixed = fix_text(ch['content'])
            chunks.append({**ch, "content": fixed, "chunk_key": f"{key}:{ch['start_sec']}:{digest[:16]}",
                           "content_hash": hashlib.sha256(fixed.encode()).hexdigest(), "search_text": fixed})
        records.append((source, chunks))
    return records


def sync_supabase(client, source: dict, chunks: list[dict], embed: bool) -> int:
    existing = client.table('knowledge_sources').select('id,meta_json').eq('source_key', source['source_key']).execute().data
    if existing:
        meta = existing[0].get('meta_json') or {}
        if not meta.get('provisional'):
            print(f"skip canonical: {source['source_key']}")
            return 0
        if meta.get('content_sha256') != source['meta_json']['content_sha256']:
            raise RuntimeError(f"字幕変更を検出。差し替え確認が必要: {source['source_key']}")
        sid = existing[0]['id']
    else:
        sid = client.table('knowledge_sources').insert(source).execute().data[0]['id']
    old = client.table('knowledge_chunks').select('chunk_key').eq('source_id', sid).execute().data
    keys = {r['chunk_key'] for r in old}
    payload = [{**ch, 'source_id': sid} for ch in chunks if ch['chunk_key'] not in keys]
    for i in range(0, len(payload), 100):
        client.table('knowledge_chunks').upsert(payload[i:i+100], on_conflict='chunk_key').execute()
    if embed:
        ready = {r['chunk_key'] for r in client.table('knowledge_chunks').select('chunk_key').eq('source_id', sid).not_.is_('embedding', 'null').execute().data}
        pending = [ch for ch in chunks if ch['chunk_key'] not in ready]
        for i in range(0, len(pending), 30):
            batch = pending[i:i+30]
            vectors = batch_embed_texts([r['content'] for r in batch])
            rows = [{**ch, 'source_id': sid, 'embedding': vector} for ch, vector in zip(batch, vectors)]
            client.table('knowledge_chunks').upsert(rows, on_conflict='chunk_key', returning='minimal').execute()
    return len(payload)


def sync_raimo(base: str, source: dict, chunks: list[dict], cache: dict) -> int:
    # 追加のみ。失敗時は再実行で不足分だけ再開（既存チャンクを削除しない）。
    if 'sources' not in cache:
        cache['sources'] = get_json(base, '/knowledge-sources').get('sources') or []
        cache['keys'] = {r.get('chunk_key') for r in get_json(base, '/knowledge-chunks').get('chunks') or []}
    sources = cache['sources']
    old_source = next((s for s in sources if s.get('source_key') == source['source_key']), None)
    if old_source:
        meta = old_source.get('meta_json') or '{}'
        if isinstance(meta, str):
            meta = json.loads(meta)
        if not meta.get('provisional'):
            if not meta.get('file_sha256') or meta['file_sha256'] != source['meta_json'].get('file_sha256'):
                return 0
        elif meta.get('content_sha256') != source['meta_json']['content_sha256']:
            raise RuntimeError(f"Raimo字幕変更を検出: {source['source_key']}")
    else:
        row = {**source, 'meta_json': json.dumps(source['meta_json'], ensure_ascii=False)}
        status, _ = post_json(base, '/admin/knowledge-sources', row)
        if not 200 <= status < 300:
            raise RuntimeError(f'Raimo source HTTP {status}')
        sources.append(source)
    keys = cache['keys']
    pending = [ch for ch in chunks if ch['chunk_key'] not in keys]

    def send(ch):
        row = {k: ch[k] for k in ('chunk_key','start_sec','end_sec','speaker','content','search_text')}
        row['source_key'] = source['source_key']
        # 応答不明のPOSTを盲目的に再送しない。次回起動時に既存キーを確認する。
        status, _ = post_json(base, '/admin/knowledge-chunks', row)
        if not 200 <= status < 300:
            raise RuntimeError(f"Raimo chunk HTTP {status}: {ch['chunk_key']}")
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(send, pending))
    keys.update(ch['chunk_key'] for ch in pending)
    return len(pending)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', type=Path, default=REPO/'apps/jarvis-dashboard/data/kiso_course_status.json')
    ap.add_argument('--input-dir', type=Path, help='取得済みMD。未指定ならOneDrive Graphから取得')
    ap.add_argument('--graph-root', default='215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/基礎講座_文字起こし/jarvis')
    ap.add_argument('--course', default='神大家1.基礎')
    ap.add_argument('--slug', action='append')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--embed', action='store_true')
    ap.add_argument('--mirror-raimo', action='store_true')
    args = ap.parse_args()
    load_env()
    if args.apply and os.environ.get('SUPABASE_URL', '').rstrip('/') != 'https://mwubzgefkkjjbingrmqu.supabase.co':
        raise RuntimeError('接続先が kamiooya-qa ではありません。SUPABASE_URLを確認してください')
    manifest = json.loads(args.manifest.read_text())
    lessons = [r for r in manifest['lessons'] if not args.slug or r['slug'] in args.slug]
    if args.slug and set(args.slug) - {r['slug'] for r in lessons}:
        raise RuntimeError('manifestに存在しないslugが指定されています')
    client = get_client() if args.apply else None
    base = os.environ.get('RAIMO_APP_URL') or os.environ.get('LIMO_APP_URL') or ''
    if args.mirror_raimo and not base:
        raise RuntimeError('RAIMO_APP_URL missing')
    from jarvis_onedrive_graph import read_file_graph
    totals = {'lessons': 0, 'videos': 0, 'chunks': 0, 'no_subtitles': 0, 'supabase_added': 0, 'raimo_added': 0}
    raimo_cache = {}
    for lesson in lessons:
        name = lesson.get('jarvis_file') or f"基礎講座文字起こし_{lesson['slug']}.md"
        origin = args.graph_root.rstrip('/') + '/' + name
        text = ((args.input_dir/name).read_text() if args.input_dir else retry(lambda: read_file_graph(origin)).decode('utf-8-sig'))
        records = build_records(lesson, text, origin, args.course)
        if lesson.get('status') == 'vtt_ready' and not records:
            raise RuntimeError(f"字幕ありmanifestと本文の不一致: {lesson['slug']}")
        totals['lessons'] += 1
        totals['no_subtitles'] += int(not records)
        for source, chunks in records:
            totals['videos'] += 1
            totals['chunks'] += len(chunks)
            if args.apply:
                totals['supabase_added'] += sync_supabase(client, source, chunks, args.embed)
                if args.mirror_raimo:
                    totals['raimo_added'] += sync_raimo(base, source, chunks, raimo_cache)
            print(json.dumps({'source': source['source_key'], 'chunks': len(chunks), 'applied': args.apply}, ensure_ascii=False), flush=True)
    print(json.dumps(totals, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
