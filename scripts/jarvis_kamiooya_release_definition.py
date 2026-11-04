#!/usr/bin/env python3
"""Generate guarded Raimo definitions. Resolved runtime secrets stay in private output."""
from __future__ import annotations
import argparse,copy,os,re
from pathlib import Path
import yaml
from jarvis_kamiooya_guard_raimo import guard_definition


def release_definition(source:dict)->dict:
    result=guard_definition(source)
    for route in result['api']:
        if route['name'] in ('listApprovedUsers','listPendingUsers'):
            route['steps']=[s for s in route['steps'] if s.get('check',{}).get('errorCode')!='security_maintenance']
    # Never include internal role/transfer records in community lists or AI retrieval.
    for route in result['api']:
        if route['name'] in ('listComments','sendMessage','sendMessageFast','sendMessageSemantic','sendMessageSemanticFast'):
            for step in route['steps']:
                query=step.get('tableFetchMany',{})
                if query.get('table')=='comments':
                    raw=query.get('whereRaw',{'sql':'1=1','params':[]})
                    raw['sql']='('+raw['sql']+") AND COALESCE(source_type,'') NOT IN ('__admin_meta__','__master_xfer__') AND comment_id NOT LIKE 'admin_%'"
                    query['whereRaw']=raw
    reads=[]
    for route in result['api']:
        if route['endpoint'].startswith('GET '):
            clone=copy.deepcopy(route);clone['name']='gatewayRead_'+route['name'];clone['endpoint']='POST /internal/read'+route['endpoint'][4:];reads.append(clone)
    result['api']+=reads
    for field in ('email','user_id','reset_token'):
        key='id' if field=='user_id' else field
        result['api'].append({'name':'gatewayAuthLookup_'+field,'endpoint':'POST /internal/auth-user/'+field,
          'steps':[{'check':{'condition':"input.__gateway_secret == '__RAIMO_AUTH_GATEWAY_SECRET__'",'errorCode':'unauthorized','errorMessage':"'認証できません'"}},
                   {'tableFetchOne':{'table':'users','where':{key:'input.'+field}},'as':'user'}],
          'output':{'user':'fetched.user'}})
    for field in ('id','comment_id'):
        result['api'].append({'name':'gatewayProtectedComment_'+field,'endpoint':'POST /internal/auth-comment/'+field,
         'steps':[{'check':{'condition':"input.__gateway_secret == '__RAIMO_AUTH_GATEWAY_SECRET__'",'errorCode':'unauthorized','errorMessage':"'認証できません'"}},
                  {'tableFetchOne':{'table':'comments','where':{field:'input.'+field}},'as':'comment'}],
         'output':{'comment':'fetched.comment'}})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=yaml.safe_dump(release_definition(yaml.safe_load(a.source.read_text())),allow_unicode=True,sort_keys=False)
    for key in set(re.findall(r'__([A-Z][A-Z0-9_]+)__',out)):
        value=os.environ.get(key,'')
        if not value:raise SystemExit('missing runtime configuration: '+key)
        out=out.replace('__'+key+'__',value)
    a.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:f.write(out)
    print('guarded private release definition written')
if __name__=='__main__':main()
