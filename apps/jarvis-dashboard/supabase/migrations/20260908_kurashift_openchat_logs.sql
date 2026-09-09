-- 神大家さんクラブ LINEオープンチャット知見・修繕業者相談ログ
-- jarvis-dashboard (idkdqneutpvkhxhpjtgc)

create table if not exists public.kurashift_openchat_logs (
  id text primary key,
  route_id text not null,
  chat_name text not null,
  stream_type text not null default 'main' check (stream_type in ('main', 'thread', 'thread_reply')),
  thread_title text,
  posted_at timestamptz,
  post_date date,
  sender_name text,
  content text not null,
  is_repair_related boolean not null default false,
  repair_category text,
  area text,
  extracted_vendors jsonb not null default '[]'::jsonb,
  recommend_notes text,
  raw_message_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists kurashift_openchat_logs_route_idx
  on public.kurashift_openchat_logs (route_id, posted_at desc nulls last);

create index if not exists kurashift_openchat_logs_repair_idx
  on public.kurashift_openchat_logs (is_repair_related, posted_at desc nulls last);

create index if not exists kurashift_openchat_logs_date_idx
  on public.kurashift_openchat_logs (post_date desc nulls last);

-- RLS設定（authenticated に全権限・anon遮断）
alter table public.kurashift_openchat_logs enable row level security;

drop policy if exists kurashift_openchat_logs_auth_all on public.kurashift_openchat_logs;
create policy kurashift_openchat_logs_auth_all
  on public.kurashift_openchat_logs
  for all to authenticated
  using (true)
  with check (true);
