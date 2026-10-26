#!/usr/bin/env python3
"""取り込み結果の読取専用照合。字幕ありレッスン・embedding・Raimo欠損を検出。"""
import argparse
import json
import os

from import_vimeo_transcripts import REPO
from embed_to_supabase import load_env, get_client
from mirror_knowledge_to_raimo import get_json


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', default=str(REPO/'apps/jarvis-dashboard/data/kiso_course_status.json'))
    ap.add_argument('--course', default='神大家1.基礎')
    args = ap.parse_args()
    load_env()
    client = get_client()
    sources = client.table('knowledge_sources').select('id,source_key,meta_json').like('source_key','westudy:%').execute().data
    sources = [s for s in sources if (s.get('meta_json') or {}).get('course') == args.course]
    with open(args.manifest) as f:
        lessons = json.load(f)['lessons']
    expected = {r['slug'] for r in lessons if r.get('status') == 'vtt_ready'}
    actual = {s['meta_json']['lesson_slug'] for s in sources}
    keys = set()
    pending = 0
    for source in sources:
        offset = 0
        while True:
            rows = client.table('knowledge_chunks').select('chunk_key').eq('source_id',source['id']).range(offset,offset+999).execute().data
            keys.update(r['chunk_key'] for r in rows)
            if len(rows) < 1000:
                break
            offset += 1000
        result = client.table('knowledge_chunks').select('id',count='exact').eq('source_id',source['id']).is_('embedding','null').limit(0).execute()
        pending += result.count or 0
    base = os.environ.get('RAIMO_APP_URL') or os.environ.get('LIMO_APP_URL')
    remote = get_json(base,'/knowledge-chunks').get('chunks') or []
    source_keys = {s['source_key'] for s in sources}
    remote_keys = {r['chunk_key'] for r in remote if r.get('source_key') in source_keys}
    summary = {'expected_lessons':len(expected),'imported_lessons':len(actual),
               'missing_lessons':sorted(expected-actual),'videos':len(sources),'supabase_chunks':len(keys),
               'raimo_chunks':len(remote_keys),'missing_in_raimo':len(keys-remote_keys),
               'extra_in_raimo':len(remote_keys-keys),'pending_embeddings':pending}
    print(json.dumps(summary,ensure_ascii=False))
    return int(bool(expected-actual or keys != remote_keys or pending or not keys))


if __name__ == '__main__':
    raise SystemExit(main())
