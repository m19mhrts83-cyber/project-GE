#!/usr/bin/env python3
"""Recover original WeStudy images without re-encoding or deleting thumbnails. Dry run by default."""
from __future__ import annotations
import argparse,hashlib,io,json,re,os,threading,math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,unquote
from datetime import datetime,timezone
import requests
from PIL import Image
from jarvis_kamiooya_attachments import Store,MAX_BYTES,BUCKET


def original_url(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname not in ('westudy.co.jp','www.westudy.co.jp') or u.username or u.password or u.port or u.query or u.fragment:
        return None
    if not u.path.startswith('/wp-content/uploads/'):
        return None
    path,n=re.subn(r'-\d+x\d+(?=\.(?:jpg|jpeg|png|webp)$)','',u.path,flags=re.I)
    return urlunsplit((u.scheme,u.netloc,path,'','')) if n else None


def image_info(data):
    with Image.open(io.BytesIO(data)) as im:
        if im.format not in ('JPEG','MPO','PNG','WEBP') or im.width*im.height>60_000_000:
            raise ValueError('unsupported_image')
        size=im.size;fmt=im.format;im.verify()
    return size,{'MPO':('image/jpeg','.jpg'),'JPEG':('image/jpeg','.jpg'),'PNG':('image/png','.png'),'WEBP':('image/webp','.webp')}[fmt]


def download(url,transport=requests):
    with transport.get(url,stream=True,allow_redirects=False,timeout=(10,40)) as r:
        if r.status_code==404:return None
        if r.status_code!=200:raise RuntimeError('source_http_'+str(r.status_code))
        total=0;parts=[]
        for chunk in r.iter_content(65536):
            total+=len(chunk)
            if total>MAX_BYTES:raise ValueError('file_size_limit')
            parts.append(chunk)
        return b''.join(parts)


class StorageBudget:
    def __init__(self,used):
        if type(used) not in (int,float) or not math.isfinite(used):raise ValueError('unknown_storage_usage')
        self.used=used;self.lock=threading.Lock()
    def reserve(self,size):
        with self.lock:
            if self.used+size>80_000_000_000:return False
            self.used+=size;return True


def recover(store,row,apply=False,budget=None,source_transport=None):
    url=original_url(row['source_url'])
    if not url:return {'result':'not_thumbnail'}
    if row.get('original_source_url'):return {'result':'already_original'}
    data=download(url,source_transport or requests)
    if data is None:return {'result':'source_missing'}
    (w,h),(mime,ext)=image_info(data)
    thumb=re.search(r'-(\d+)x(\d+)(?=\.[a-z]+$)',row['source_url'],re.I)
    tw,th=map(int,thumb.groups())
    if w<tw or h<th or (w==tw and h==th):return {'result':'not_larger'}
    digest=hashlib.sha256(data).hexdigest()
    meta={k:row[k] for k in ['id','comment_id','bucket','source_url']}
    meta.update(original_name=Path(unquote(urlsplit(url).path)).name[:255],content_type=mime,byte_size=len(data),sha256=digest,
                storage_path=f"comments/{row['comment_id']}/{digest}{ext}",original_source_url=url,image_width=w,image_height=h)
    if apply:
        if budget is not None:
            allowed=budget.reserve(len(data))
        else:
            usage=store.request('POST','/rest/v1/rpc/openchat_backup_storage_bytes',json={}).json()
            allowed=isinstance(usage,(int,float)) and usage+len(data)<=80_000_000_000
        if not allowed:return {'result':'budget_held'}
        store.save(meta,data,old_record=row)
    return {'result':'saved' if apply else 'available','bytes':len(data),'previous_bytes':row['byte_size'],'width':w,'height':h}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--apply',action='store_true');p.add_argument('--comment-id');p.add_argument('--limit',type=int,default=1);p.add_argument('--workers',type=int,default=3)
    a=p.parse_args(argv)
    if not 1<=a.limit<=5000:p.error('limit must be 1..5000')
    if not 1<=a.workers<=4:p.error('workers must be 1..4')
    store=Store();rows=[]
    for offset in range(0,10000,1000):
        params={'select':'*','order':'id.asc','limit':1000,'offset':offset}
        if a.comment_id:params['comment_id']='eq.'+a.comment_id
        batch=store.request('GET','/rest/v1/community_attachments',params=params).json();rows+=batch
        if len(batch)<1000:break
    counts={};records=[]
    selected=[r for r in rows if original_url(r['source_url']) and not r.get('original_source_url')][:a.limit]
    budget=StorageBudget(store.request('POST','/rest/v1/rpc/openchat_backup_storage_bytes',json={}).json()) if a.apply else None
    local=threading.local()
    def work(row):
        try:
            if not hasattr(local,'store'):
                local.store=Store();local.source=requests.Session()
            result=recover(local.store,row,a.apply,budget,local.source)
        except Exception as e:result={'result':'failed','error_type':type(e).__name__}
        return {'id':row['id'],**result}
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for result in pool.map(work,selected):
            records.append(result);counts[result['result']]=counts.get(result['result'],0)+1
            report={'at':datetime.now(timezone.utc).isoformat(),'apply':a.apply,'counts':counts,'records':records}
            a.report.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            temp=a.report.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2));os.chmod(temp,0o600);os.replace(temp,a.report)
            if len(records)%25==0:print(json.dumps({'processed':len(records),'counts':counts}),flush=True)
    if not records:
        a.report.parent.mkdir(parents=True,exist_ok=True,mode=0o700);a.report.write_text(json.dumps({'counts':counts,'records':[]}));os.chmod(a.report,0o600)
    print(json.dumps({'selected':len(records),'counts':counts}),flush=True)
    return 1 if counts.get('failed') else 0
if __name__=='__main__':raise SystemExit(main())
