#!/usr/bin/env python3
"""照合済みNotta受領manifestから不足字幕を追加。既定プレビュー、--applyで本番接続。"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from import_vimeo_transcripts import REPO, sync_raimo
from embed_to_supabase import load_env, get_client, batch_embed_texts
from notta_to_knowledge import parse_xlsx, chunk_cues
from transcript_corrections import fix_text


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-dir', type=Path, required=True)
    ap.add_argument('--manifest', type=Path, default=REPO/'config/kamiooya_notta_received_20261027.json')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    load_env()
    manifest = json.loads(args.manifest.read_text())
    client = get_client()
    if os.environ['SUPABASE_URL'].rstrip('/') != 'https://mwubzgefkkjjbingrmqu.supabase.co':
        raise RuntimeError('kamiooya-qa以外への接続を拒否')
    base = os.environ.get('RAIMO_APP_URL') or os.environ.get('LIMO_APP_URL')
    cache = {}
    totals = {'videos':0,'chunks':0,'supabase_added':0,'raimo_added':0}
    for video in manifest['videos']:
        path = args.input_dir/video['file']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        cues, warnings = parse_xlsx(path)
        if warnings or not cues or cues[-1].start_sec == 0:
            raise RuntimeError(f'時刻付き字幕を確認できません: {path.name}: {warnings}')
        key = f"notta:westudy:{video['slug']}:vimeo:{video['video_id']}"
        meta = {'transcript_provider':'notta','provisional':False,'course':'神大家1.基礎',
                'lesson_slug':video['slug'],'lesson_url':f"https://westudy.co.jp/lesson/{video['slug']}",
                'origin_filename':path.name,'file_sha256':digest,'chatwork_file_id':manifest['chatwork_file_id'],
                'received_at':manifest['received_at'],'correction_rules':'kamiooya_transcript_corrections.tsv'}
        source = {'source_key':key,'source_kind':'video','content_channel':'seminar_video',
                  'title':video['title'],'video_id':video['video_id'],'video_url':f"https://vimeo.com/{video['video_id']}",
                  'origin_path':str(path),'ingest_status':'ready','meta_json':meta}
        chunks=[]
        for row in chunk_cues(cues,max_sec=90,max_chars=1000):
            text=fix_text(row['content'])
            h=hashlib.sha256(text.encode()).hexdigest()
            chunks.append({**row,'content':text,'search_text':text,'content_hash':h,
                           'chunk_key':f"{key}:{row['start_sec']}:{h[:16]}"})
        existing = client.table('knowledge_sources').select('id,source_key,meta_json').eq('video_id',video['video_id']).execute().data
        if any(s['source_key'] != key for s in existing):
            raise RuntimeError(f'既存動画の上書き・二重登録を拒否: {video["video_id"]}')
        if existing and existing[0]['meta_json'].get('file_sha256') != digest:
            raise RuntimeError('受領原本の変更を検出。差替確認が必要')
        if args.apply:
            sid = existing[0]['id'] if existing else client.table('knowledge_sources').insert(source).execute().data[0]['id']
            ready = {r['chunk_key'] for r in client.table('knowledge_chunks').select('chunk_key').eq('source_id',sid).not_.is_('embedding','null').execute().data}
            pending=[r for r in chunks if r['chunk_key'] not in ready]
            for i in range(0,len(pending),30):
                batch=pending[i:i+30]
                vectors=batch_embed_texts([r['content'] for r in batch])
                client.table('knowledge_chunks').upsert([{**r,'source_id':sid,'embedding':v} for r,v in zip(batch,vectors)],on_conflict='chunk_key').execute()
            totals['supabase_added']+=len(pending)
            totals['raimo_added']+=sync_raimo(base,source,chunks,cache)
        totals['videos']+=1;totals['chunks']+=len(chunks)
        print(json.dumps({'file':path.name,'key':key,'cues':len(cues),'chunks':len(chunks),'applied':args.apply},ensure_ascii=False),flush=True)
    print(json.dumps(totals),flush=True)


if __name__=='__main__':
    main()
