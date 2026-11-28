// Optional local PostgreSQL integration: NODE_PATH=<temporary install>/node_modules node --test <this file>
// Test-only dependency: @electric-sql/pglite. Never connects to production.
// AIナビの記録（オプチャ記録・検索記録）を、ログインした人・anon が読めず、service_role だけが読めること（2026-11-28）。
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const {PGlite}=createRequire(import.meta.url)('@electric-sql/pglite');
const migration=readFileSync(new URL('../../apps/kamiooya-qa-web/supabase/migrations/20261128_revoke_member_reads_openchat_search.sql',import.meta.url),'utf8');

test('real PostgreSQL: member and anon reads of openchat/search logs are removed, service_role keeps them',async()=>{
 const db=new PGlite();
 try{
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
   create schema extensions; create domain extensions.vector as text;
   grant usage on schema public to anon,authenticated,service_role;
   create table public.line_openchat_logs(id text primary key,ingest_status text,content text);
   alter table public.line_openchat_logs enable row level security;
   create policy line_openchat_logs_auth_select on public.line_openchat_logs for select to authenticated using (ingest_status='ready');
   create table public.app_qa_search_events(id bigint primary key,query_text text,user_id text);
   alter table public.app_qa_search_events enable row level security;
   create policy events_all on public.app_qa_search_events for select to authenticated using (true);
   create view public.app_qa_search_mode_daily as select count(*) from public.app_qa_search_events;
   grant all on public.line_openchat_logs, public.app_qa_search_events, public.app_qa_search_mode_daily to anon, authenticated, service_role;
   create function public.search_openchat_keyword(query_text text, match_count int) returns setof public.line_openchat_logs
    language sql stable as $$ select * from public.line_openchat_logs where ingest_status='ready' $$;
   create function public.match_openchat_semantic(query_embedding extensions.vector, match_threshold float, match_count int) returns setof public.line_openchat_logs
    language sql stable as $$ select * from public.line_openchat_logs $$;
   grant execute on function public.search_openchat_keyword(text,int), public.match_openchat_semantic(extensions.vector,float,int) to authenticated, service_role;
   insert into public.line_openchat_logs values ('a','ready','x'); insert into public.app_qa_search_events values (1,'q','u');`);
  await db.exec('set role authenticated');
  assert.equal((await db.query('select * from line_openchat_logs')).rows.length,1); // 直す前は読めてしまう
  await db.exec('reset role');
  await db.exec(migration);await db.exec(migration);
  for(const role of ['anon','authenticated']){
   await db.exec('set role '+role);
   for(const sql of ['select * from line_openchat_logs','select * from app_qa_search_events','select * from app_qa_search_mode_daily',
     "select * from search_openchat_keyword('x',5)","select * from match_openchat_semantic('v',0.1,5)"])
    await assert.rejects(db.query(sql),/permission denied/,role+': '+sql);
   await db.exec('reset role');
  }
  assert.equal((await db.query("select count(*)::int n from pg_policies where tablename='line_openchat_logs'")).rows[0].n,0);
  await db.exec('set role service_role');
  assert.equal((await db.query('select * from line_openchat_logs')).rows.length,1);
  assert.equal((await db.query('select * from app_qa_search_events')).rows.length,1);
  assert.equal((await db.query("select * from search_openchat_keyword('x',5)")).rows.length,1);
  assert.equal((await db.query("select * from match_openchat_semantic('v',0.1,5)")).rows.length,1);
  await db.exec('reset role');
 }finally{await db.close();}
});

test('real PostgreSQL: the migration also runs where the tables and functions do not exist yet',async()=>{
 const db=new PGlite();
 try{
  await db.exec('create role anon; create role authenticated; create role service_role; create schema extensions;');
  await db.exec(migration);
 }finally{await db.close();}
});
