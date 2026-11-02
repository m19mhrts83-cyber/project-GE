#!/usr/bin/env python3
"""Mac operational overlay: existing text runner + independently versioned backup.

Does not edit main, merge a PR, publish member access or change the schedule.
Install by pointing the existing daily LaunchAgent at a pinned local code snapshot.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
import signal

def run_bounded(command, *, env, cwd=None, timeout=900):
    """Terminate the entire stage process group, so an orphan cannot retain LINE's lock."""
    process=subprocess.Popen(command,env=env,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
      text=True,start_new_session=True)
    try:
        out,err=process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command,process.returncode,out,err)
    except subprocess.TimeoutExpired:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:out,err=process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            out,err=process.communicate()
        return subprocess.CompletedProcess(command,124,out,err)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--code-root',type=Path,required=True)
    p.add_argument('--attachments-only',action='store_true')
    p.add_argument('--limit',type=int,default=100)
    p.add_argument('--scan-pages',type=int,default=2)
    p.add_argument('--scan-threads',type=int,default=5)
    a=p.parse_args();repo=a.repo_root.resolve();code=a.code_root.resolve()
    from dotenv import dotenv_values
    env=os.environ.copy()
    for file in [repo/'.env.jarvis_private',repo/'line_unofficial_poc/.env',repo/'215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env']:
        env.update({k:v for k,v in dotenv_values(file).items() if v is not None})
    env['LINE_HOST_DOMAIN']='https://ga2.line.naver.jp'
    env['LINE_OBS_DOMAIN']='https://obs.line-apps.com'
    state=Path.home()/'.local/share/jarvis/openchat-ops';state.mkdir(parents=True,exist_ok=True,mode=0o700)
    poc=repo/'line_unofficial_poc'
    summary={};text_rc=None;paused=False
    with (state/'daily.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 75
        if subprocess.run(['pgrep','-f',r'application\.jp\.naver\.line\.mac|/Applications/LINE\.app'],capture_output=True).returncode==0:
            print(json.dumps({'state':'blocked','reason':'mac_line_running'}));return 75
        try:
            if not a.attachments_only:
                paused=True # the existing runner can pause the watcher before it fails
                text_rc=run_bounded([str(repo/'launchd/openchat_md_db_sync_runner.sh')],env=env).returncode
            subprocess.run([str(poc/'launchd/open_chat_watch_pause.sh')],check=True,capture_output=True);paused=True
            command=[str(poc/'.venv-patch/bin/python'),str(code/'scripts/jarvis_openchat_attachments.py'),'--apply','--scan',
              '--routes-yaml',str(poc/'open_chat_routes.yaml'),'--active-threads',str(poc/'.line_auth/active_thread_mids.json'),
              '--limit',str(a.limit),'--max-file-mib','50','--scan-pages',str(a.scan_pages),'--scan-threads',str(a.scan_threads)]
            result=run_bounded(command,env=env,cwd=repo)
            for line in result.stdout.splitlines():
                try:
                    value=json.loads(line)
                    if isinstance(value,dict):
                        allowed={'scan','states','archive_complete','by_kind','oldest_waiting_seconds','saved_unique_bytes',
                          'backfill_unique_bytes','daily_last30_unique_bytes','daily_observation_days',
                          'projected_monthly_bytes','project_storage_bytes'}
                        summary.update({k:v for k,v in value.items() if k in allowed})
                except ValueError:pass
            summary.update(at=datetime.now().astimezone().isoformat(),text_rc=text_rc,attachment_rc=result.returncode)
        finally:
            if paused:
                subprocess.run([str(poc/'launchd/open_chat_watch_resume.sh')],capture_output=True)
                alive=False
                for _ in range(20):
                    if subprocess.run(['pgrep','-f','chrline_open_chat_realtime_watch.py'],capture_output=True).returncode==0:
                        alive=True;break
                    time.sleep(.5)
                summary['watch_running']=alive
                if not alive:summary['requires_attention']='watch_resume_failed'
        (state/'daily_health.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        # Only summary counters reach the private Dashboard; no message identities/names.
        import requests
        key=env.get('JARVIS_SUPABASE_SERVICE_ROLE_KEY','');url=env.get('JARVIS_SUPABASE_URL','').rstrip('/')
        if key and url:
            response=requests.post(url+'/rest/v1/sync_meta',headers={'apikey':key,'Authorization':'Bearer '+key,
              'Prefer':'resolution=merge-duplicates'},json={'key':'openchat_attachment_backup_health',
              'value':json.dumps(summary,ensure_ascii=False),'updated_at':summary.get('at')},timeout=30)
            summary['dashboard_health_synced']=response.ok
        stamp=datetime.now().astimezone().strftime('%Y%m%d-%H%M')
        states=summary.get('states',{});scan=summary.get('scan',{})
        readable=(f"オプチャ添付: 保存{states.get('saved',0)}件・{summary.get('saved_unique_bytes',0)/1e6:.1f}MB、"
          f"取得不可{states.get('expired',0)}件、待機{states.get('pending',0)}件、保留{states.get('held',0)}件。"
          f"Supabase保存合計{summary.get('project_storage_bytes',0)/1e9:.3f}GB。"
          f"本文RC={text_rc}、添付RC={summary.get('attachment_rc')}、監視復帰={summary.get('watch_running')}。"
          f"過去履歴の続き{scan.get('pages_remaining',0)}ストリーム・順番待ちスレッド{scan.get('threads_deferred',0)}件。"
          "取得不可や履歴の残りがある場合、完全回収とは扱わない。")
        cli=[str(Path.home()/'selenium_env/venv/bin/python'),str(repo/'scripts/jarvis_kamiooya_work_history.py'),'--push','note',
          '--project','supabase-attachments-20261101','--item','openchat-attachments','--actor','OpenChat backup worker',
          '--event-id','openchat-daily-'+stamp,'--work-date',datetime.now().astimezone().strftime('%Y-%m-%d'),'--summary',readable]
        history=subprocess.run(cli,env=env,capture_output=True)
        summary['dashboard_history_synced']=history.returncode==0
        print(json.dumps(summary,ensure_ascii=False))
        return 0 if text_rc in (None,0) and summary.get('attachment_rc')==0 and summary.get('watch_running') else 1

if __name__=='__main__':raise SystemExit(main())
