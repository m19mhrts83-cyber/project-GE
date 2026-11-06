// Optional local PostgreSQL integration: NODE_PATH=<temporary install>/node_modules node --test <this file>
// Test-only dependency: @electric-sql/pglite. Never connects to production.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const {PGlite}=createRequire(import.meta.url)('@electric-sql/pglite');

test('real PostgreSQL: saved attachments have exact, searchable sources, private delivery and repeatable migration',async()=>{
 const db=new PGlite();
 try{
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
   create schema storage;
   create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint);
   create table storage.objects(bucket_id text,metadata jsonb);
   create table public.line_openchat_logs(id text primary key,route_id text,chat_title text,chat_name text,
    stream_type text,thread_title text,posted_at timestamptz,post_date date,sender_name text,content text,
    source_system text,ingest_status text,metadata jsonb,embedding text,updated_at timestamptz);
   grant usage on schema public to anon,authenticated,service_role;
   grant all on public.line_openchat_logs to service_role;`);
  const base=new URL('../../',import.meta.url);
  await db.exec(readFileSync(new URL('apps/kamiooya-qa-web/supabase/migrations/20261102_openchat_attachments.sql',base),'utf8'));
  const id='a'.repeat(64),sha='b'.repeat(64);
  await db.query(`insert into openchat_attachments(id,room_id,message_id,kind,original_name,content_type,byte_size,sha256,storage_path)
   values($1,'room','original-message','file','修繕見積.pdf','application/pdf',123,$2,$3)`,[id,sha,'objects/'+sha]);
  const migration=readFileSync(new URL('apps/kamiooya-qa-web/supabase/migrations/20261107_openchat_attachment_sources.sql',base),'utf8');
  await db.exec(migration);await db.exec(migration);
  let rows=(await db.query('select * from line_openchat_logs')).rows;
  assert.equal(rows.length,1);assert.equal(rows[0].id,'oc_'+id);
  assert.equal(rows[0].posted_at,null);assert.match(rows[0].content,/内容未解析/);
  assert.match(rows[0].content,/修繕見積.pdf/);assert.equal(rows[0].metadata.content_analyzed,false);
  await db.query(`update openchat_attachments set source_context=$1 where id=$2`,[JSON.stringify({posted_at:'2026-11-06T23:30:00+09:00',chat_title:'修繕相談',caption:'見積の資料'}),id]);
  rows=(await db.query('select * from line_openchat_logs')).rows;
  assert.equal(rows[0].post_date.toISOString().slice(0,10),'2026-11-06');assert.equal(rows[0].chat_title,'修繕相談');
  await db.query(`update line_openchat_logs set embedding='existing-vector' where id=$1`,['oc_'+id]);
  await db.exec(migration);
  assert.equal((await db.query('select embedding from line_openchat_logs')).rows[0].embedding,'existing-vector');
  assert.equal((await db.query(`select id from line_openchat_logs where content ilike '%修繕見積.pdf%' and ingest_status='ready'`)).rows.length,1);
  assert.equal((await db.query('select * from openchat_member_attachments')).rows.length,1);
  for(const role of ['anon','authenticated']){
   await db.exec('set role '+role);
   await assert.rejects(db.query('select * from openchat_member_attachments'),/permission denied/);
   await assert.rejects(db.query('select * from openchat_attachments'),/permission denied/);
   await db.exec('reset role');
  }
  await db.exec("update line_openchat_logs set ingest_status='excluded'");
  await db.exec(migration);
  assert.equal((await db.query('select * from openchat_member_attachments')).rows.length,0);
  assert.equal((await db.query('select ingest_status from line_openchat_logs')).rows[0].ingest_status,'excluded');
  await db.query(`update openchat_attachments set source_context='{"posted_at":"invalid"}' where id=$1`,[id]);
  assert.equal((await db.query('select posted_at from line_openchat_logs')).rows[0].posted_at,null);
 }finally{await db.close();}
});
