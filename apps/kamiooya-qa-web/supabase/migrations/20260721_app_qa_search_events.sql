-- Phase 13: Q&A search analytics (one-way projection from app → Supabase)
create table if not exists public.app_qa_search_events (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  search_mode text not null check (search_mode in ('normal', 'semantic')),
  query_text text not null default '',
  session_id text,
  user_id text,
  comment_hit_count integer,
  chunk_hit_count integer,
  answer_comment_count integer,
  answer_chunk_count integer,
  match_threshold double precision,
  used_sources jsonb,
  meta jsonb not null default '{}'::jsonb
);

create index if not exists app_qa_search_events_created_at_idx
  on public.app_qa_search_events (created_at desc);

create index if not exists app_qa_search_events_mode_created_idx
  on public.app_qa_search_events (search_mode, created_at desc);

-- モード別日次集計（Phase 13 第一ダッシュボード用）
create or replace view public.app_qa_search_mode_daily as
select
  (created_at at time zone 'Asia/Tokyo')::date as day_jst,
  search_mode,
  count(*)::int as event_count,
  count(distinct nullif(session_id, ''))::int as session_count
from public.app_qa_search_events
group by 1, 2;

grant select, insert on table public.app_qa_search_events to service_role;
grant select on table public.app_qa_search_events to authenticated;
grant select on public.app_qa_search_mode_daily to authenticated, service_role;
