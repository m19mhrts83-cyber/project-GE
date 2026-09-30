-- 神大家 LINEオープンチャット知見（仕込み用・検索公開は次ステップ）
-- kamiooya-qa (mwubzgefkkjjbingrmqu)
-- Q&A comments 検索にはまだ載せない。ingest_status=staging で保持。

create table if not exists public.line_openchat_logs (
  id text primary key,
  route_id text not null,
  chat_title text not null,
  chat_name text not null,
  stream_type text not null default 'main',
  thread_title text,
  posted_at timestamptz,
  post_date date,
  sender_name text,
  content text not null,
  is_repair_related boolean not null default false,
  repair_category text,
  source_system text not null default 'line_openchat',
  ingest_status text not null default 'staging',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists line_openchat_logs_title_idx
  on public.line_openchat_logs (chat_title, post_date desc nulls last);

create index if not exists line_openchat_logs_route_idx
  on public.line_openchat_logs (route_id, post_date desc nulls last);

create index if not exists line_openchat_logs_repair_idx
  on public.line_openchat_logs (is_repair_related, post_date desc nulls last);

alter table public.line_openchat_logs enable row level security;

drop policy if exists line_openchat_logs_auth_select on public.line_openchat_logs;
create policy line_openchat_logs_auth_select
  on public.line_openchat_logs
  for select to authenticated
  using (true);

grant select, insert, update, delete on table public.line_openchat_logs to service_role;
revoke all on table public.line_openchat_logs from anon;
