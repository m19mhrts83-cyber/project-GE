-- line_openchat_logs: publish 状態 + 検索（キーワード／意味）
-- kamiooya-qa (mwubzgefkkjjbingrmqu)

-- ingest_status: staging（仕込み） / ready（検索公開） / excluded（ノイズ除外）
alter table public.line_openchat_logs
  drop constraint if exists line_openchat_logs_ingest_status_check;

alter table public.line_openchat_logs
  add constraint line_openchat_logs_ingest_status_check
  check (ingest_status in ('staging', 'ready', 'excluded', 'active'));

-- 旧 active は staging 扱い（publish で ready 化）
update public.line_openchat_logs
set ingest_status = 'staging'
where ingest_status = 'active';

create index if not exists line_openchat_logs_status_posted_idx
  on public.line_openchat_logs (ingest_status, posted_at desc nulls last, post_date desc nulls last);

create index if not exists line_openchat_logs_status_title_idx
  on public.line_openchat_logs (ingest_status, chat_title, post_date desc nulls last);

-- embedding（comments / knowledge_chunks と同系 768）
alter table public.line_openchat_logs
  add column if not exists embedding extensions.vector(768);

create index if not exists line_openchat_logs_embedding_ivfflat_idx
  on public.line_openchat_logs using ivfflat (embedding extensions.vector_cosine_ops)
  with (lists = 100);

-- RLS: 認証ユーザーは ready のみ参照
drop policy if exists line_openchat_logs_auth_select on public.line_openchat_logs;
create policy line_openchat_logs_auth_select
  on public.line_openchat_logs
  for select to authenticated
  using (ingest_status = 'ready');

-- キーワード検索（ready のみ）
create or replace function public.search_openchat_keyword(
  query_text text,
  match_count int default 20
)
returns table (
  id text,
  route_id text,
  chat_title text,
  chat_name text,
  stream_type text,
  thread_title text,
  posted_at timestamptz,
  post_date date,
  sender_name text,
  content text,
  similarity float
)
language sql
stable
set search_path = public, extensions
as $$
  select
    o.id,
    o.route_id,
    o.chat_title,
    o.chat_name,
    o.stream_type,
    o.thread_title,
    o.posted_at,
    o.post_date,
    o.sender_name,
    o.content,
    0.5::float as similarity
  from public.line_openchat_logs o
  where o.ingest_status = 'ready'
    and length(trim(coalesce(query_text, ''))) > 0
    and (
      o.content ilike '%' || query_text || '%'
      or o.chat_title ilike '%' || query_text || '%'
      or o.chat_name ilike '%' || query_text || '%'
      or coalesce(o.sender_name, '') ilike '%' || query_text || '%'
      or coalesce(o.thread_title, '') ilike '%' || query_text || '%'
    )
  order by coalesce(o.posted_at, o.post_date::timestamptz) desc nulls last
  limit greatest(1, least(coalesce(match_count, 20), 50));
$$;

-- 意味検索（ready かつ embedding あり）
create or replace function public.match_openchat_semantic(
  query_embedding extensions.vector(768),
  match_threshold float default 0.22,
  match_count int default 20
)
returns table (
  id text,
  route_id text,
  chat_title text,
  chat_name text,
  stream_type text,
  thread_title text,
  posted_at timestamptz,
  post_date date,
  sender_name text,
  content text,
  similarity float
)
language sql
stable
set search_path = public, extensions
as $$
  select
    o.id,
    o.route_id,
    o.chat_title,
    o.chat_name,
    o.stream_type,
    o.thread_title,
    o.posted_at,
    o.post_date,
    o.sender_name,
    o.content,
    1 - (o.embedding <=> query_embedding) as similarity
  from public.line_openchat_logs o
  where o.ingest_status = 'ready'
    and o.embedding is not null
    and 1 - (o.embedding <=> query_embedding) >= match_threshold
  order by o.embedding <=> query_embedding
  limit greatest(1, least(coalesce(match_count, 20), 50));
$$;

grant execute on function public.search_openchat_keyword(text, int) to authenticated, service_role;
grant execute on function public.match_openchat_semantic(extensions.vector, float, int) to authenticated, service_role;
