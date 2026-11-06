#!/usr/bin/env python3
"""Add a bounded read alias to an existing guarded Raimo definition. Local preparation only."""
import argparse,copy,os
from pathlib import Path
import yaml

def add_page_route(source):
    result=copy.deepcopy(source)
    old=next(r for r in result['api'] if r['endpoint']=='POST /internal/read/comments')
    if any(r['endpoint']=='POST /internal/read/comments-page' for r in result['api']):
        raise ValueError('page_route_already_exists')
    checks=[copy.deepcopy(s) for s in old['steps'] if 'check' in s]
    if not checks:raise ValueError('guard_required')
    route={'name':'internalReadCommentsPage','endpoint':'POST /internal/read/comments-page','steps':checks+[{'tableFetchMany':{'table':'comments','orderBy':'id ASC','limit':500,'whereRaw':{'sql':"id > ? AND COALESCE(source_type,'') NOT IN ('__admin_meta__','__master_xfer__') AND comment_id NOT LIKE 'admin_%'",'params':['input.after_id']}},'as':'comments'}],'output':{'comments':'fetched.comments'}}
    result['api'].append(route)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(yaml.safe_dump(add_page_route(yaml.safe_load(a.source.read_text())),allow_unicode=True,sort_keys=False));os.chmod(a.output,0o600)
    print('Prepared bounded read alias locally; not published.')
