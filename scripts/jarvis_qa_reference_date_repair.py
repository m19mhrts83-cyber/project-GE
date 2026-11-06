#!/usr/bin/env python3
"""Repair only missing Supabase reference dates from an audited Raimo export. Dry-run default."""
from __future__ import annotations
import argparse,json,re,os
from pathlib import Path
from datetime import datetime,timezone,timedelta
from jarvis_kamiooya_attachments import Store

def source_date(raw):
    value=str(raw or '').strip()
    if not re.fullmatch(r'\d{4}[-/]\d{2}[-/]\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?',value):return None
    try:
        parsed=datetime.fromisoformat(value.replace('/','-').replace('Z','+00:00'))
        if not 1900<=parsed.year<=2100:return None
        if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone(timedelta(hours=9)))
        return parsed.isoformat()
    except ValueError:return None

def plan(source,existing):
    dates={};conflicts=set();invalid=0
    for row in source:
        ident=str(row.get('comment_id') or '').strip()
        if not ident or ident.startswith('admin_') or row.get('source_type') in ('__admin_meta__','__master_xfer__'):continue
        value=source_date(row.get('posted_at'))
        if not value:invalid+=1;continue
        if ident in dates and dates[ident]!=value:conflicts.add(ident)
        dates[ident]=value
    repairs=[]
    for row in existing:
        ident=str(row['comment_id'])
        if row.get('posted_at') or ident not in dates or ident in conflicts:continue
        repairs.append({'comment_id':ident,'posted_at':dates[ident]})
    return repairs,{'source_undated_or_invalid':invalid,'conflicting_ids':len(conflicts),'existing_count':len(existing),'repair_candidates':len(repairs)}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args(argv)
    source=json.loads(a.source.read_text());store=Store();rows=[]
    for offset in range(0,100000,1000):
        part=store.request('GET','/rest/v1/comments',params={'select':'comment_id,posted_at','order':'comment_id.asc','limit':1000,'offset':offset}).json();rows+=part
        if len(part)<1000:break
    else:raise ValueError('metadata_scan_limit')
    repairs,counts=plan(source,rows)
    a.report.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    snapshot=a.report.with_name(a.report.stem+'-audit-private.json');snapshot.write_text(json.dumps(repairs));os.chmod(snapshot,0o600)
    updated=0
    if a.apply:
        for offset in range(0,len(repairs),500):
            count=store.request('POST','/rest/v1/rpc/qa_repair_missing_reference_dates',json={'records':repairs[offset:offset+500]}).json()
            updated+=int(count)
    result={'apply':a.apply,**counts,'updated':updated}
    a.report.write_text(json.dumps(result,indent=2));os.chmod(a.report,0o600);print(json.dumps(result))
    return 0
if __name__=='__main__':raise SystemExit(main())
