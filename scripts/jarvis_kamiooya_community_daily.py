#!/usr/bin/env python3
"""Back up new community attachments from full daily harvest CSVs; no browser or LLM."""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, os, tempfile
from pathlib import Path
from urllib.parse import urlsplit, unquote
import requests
from jarvis_kamiooya_attachments import Store, build_attachment, normalize_comment_id, canonical_url
from jarvis_kamiooya_image_originals import StorageBudget, download, original_url, image_info


def trusted_upload(url):
    try:
        u=urlsplit(url)
        return (u.scheme=='https' and u.hostname in ('westudy.co.jp','www.westudy.co.jp')
                and not (u.username or u.password or u.port or u.query or u.fragment)
                and u.path.startswith('/wp-content/uploads/')
                and '..' not in unquote(u.path).split('/'))
    except ValueError:
        return False


def candidates(root):
    result={};files=0
    for path in sorted(root.rglob('*.csv')):
        if not path.resolve().is_relative_to(root.resolve()):raise ValueError('csv_outside_root')
        with path.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            if not {'comment_id','attachments_json'} <= set(reader.fieldnames or []):continue
            files+=1
            for row in reader:
                cid=normalize_comment_id(row['comment_id'])
                attachments=json.loads(row.get('attachments_json') or '[]')
                if not isinstance(attachments,list):raise ValueError('invalid_attachment_list')
                for a in attachments:
                    url=a['url']
                    ident=hashlib.sha256(f'{cid}\0{canonical_url(url)}'.encode()).hexdigest()
                    result[ident]={'comment_id':cid,'url':url,'kind':a.get('kind')}
    if not files:raise ValueError('no_harvest_csv')
    return result


def existing_ids(store):
    ids=set()
    for offset in range(0,100000,1000):
        rows=store.request('GET','/rest/v1/community_attachments',params={'select':'id','order':'id.asc','offset':offset,'limit':1000}).json()
        ids.update(r['id'] for r in rows)
        if len(rows)<1000:return ids
    raise ValueError('metadata_scan_limit')


def sync(rows,store,apply=False,max_files=200,source=None):
    counts=collections.Counter();known=existing_ids(store)
    budget=StorageBudget(store.request('POST','/rest/v1/rpc/openchat_backup_storage_bytes',json={}).json()) if apply else None
    transport=source or requests.Session();attempted=0;parents={}
    with tempfile.TemporaryDirectory(prefix='community-attachments-') as tmp:
        root=Path(tmp)
        for ident,row in sorted(rows.items()):
            if ident in known:counts['existing']+=1;continue
            if not trusted_upload(row['url']):counts['untrusted_source']+=1;continue
            cid=row['comment_id']
            if cid not in parents:parents[cid]=store.exists_comment(cid)
            if not parents[cid]:counts['parent_pending']+=1;continue
            if attempted>=max_files:counts['deferred']+=1;continue
            attempted+=1
            try:
                preferred=original_url(row['url']) if row.get('kind')=='image' else None
                data=None;provenance=None
                if preferred:
                    data=download(preferred,transport)
                    if data is not None:
                        try:
                            (w,h),_=image_info(data)
                            import re
                            m=re.search(r'-(\d+)x(\d+)(?=\.[a-z]+$)',row['url'],re.I)
                            tw,th=map(int,m.groups())
                            if w>=tw and h>=th and (w>tw or h>th):provenance=preferred
                            else:data=None
                        except ValueError:data=None
                actual=preferred if provenance else row['url']
                if data is None:data=download(actual,transport)
                if data is None:counts['source_missing']+=1;continue
                path=root/(ident+Path(unquote(urlsplit(actual).path)).suffix.lower())
                path.write_bytes(data)
                record={**row,'local_path':str(path),'name':Path(unquote(urlsplit(actual).path)).name}
                if provenance:record['original_source_url']=provenance
                meta,body=build_attachment(record,root)
                if meta['id']!=ident:raise ValueError('identity_mismatch')
                if apply:
                    if not budget.reserve(len(body)):counts['budget_held']+=1;continue
                    outcome=store.save(meta,body,old_record=None)
                else:outcome='available'
                counts[outcome]+=1
            except Exception:
                # Responses and URLs may contain private content. Report counts only.
                counts['failed']+=1
    return dict(counts)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--apply',action='store_true');p.add_argument('--max-files',type=int,default=200)
    a=p.parse_args(argv)
    if not 1<=a.max_files<=2000:p.error('max-files must be 1..2000')
    counts=sync(candidates(a.root),Store(),a.apply,a.max_files)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(counts,indent=2));os.chmod(a.report,0o600)
    print(json.dumps(counts),flush=True)
    return int(any(counts.get(k) for k in ('failed','budget_held','deferred','parent_pending')))
if __name__=='__main__':raise SystemExit(main())
