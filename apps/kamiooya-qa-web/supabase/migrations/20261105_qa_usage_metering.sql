-- エグゼラウンジ先行公開のコスト実測（2026-11-05）
-- 1) 意味検索の要約で Gemini が返した実トークン数を質問ごとに保存する
-- 2) 週ごと（JST 月曜始まり）の質問数・利用者数・トークン合計を、件数上限なしで集計する

alter table public.app_qa_search_events
  add column if not exists gemini_model text,
  add column if not exists gemini_prompt_tokens integer,
  add column if not exists gemini_output_tokens integer,
  add column if not exists gemini_thought_tokens integer,
  add column if not exists gemini_calls integer;

comment on column public.app_qa_search_events.gemini_prompt_tokens is
  'Gemini usageMetadata.promptTokenCount（意味検索の要約のみ。通常検索は Raimo 側のため null）';
comment on column public.app_qa_search_events.gemini_output_tokens is
  'Gemini usageMetadata.candidatesTokenCount';
comment on column public.app_qa_search_events.gemini_thought_tokens is
  'Gemini usageMetadata.thoughtsTokenCount（出力単価で課金される）';

-- 週次集計。p_since / p_until は timestamptz（null なら全期間）。
create or replace function public.qa_usage_weekly(
  p_since timestamptz default null,
  p_until timestamptz default null
)
returns table (
  week_start_jst date,
  search_mode text,
  ok_count integer,
  failed_count integer,
  unique_users integer,
  unique_sessions integer,
  metered_count integer,
  prompt_tokens bigint,
  output_tokens bigint,
  thought_tokens bigint
)
language sql
stable
set search_path = public
as $$
  select
    date_trunc('week', (e.created_at at time zone 'Asia/Tokyo'))::date as week_start_jst,
    e.search_mode,
    count(*) filter (where e.result_status = 'ok')::int as ok_count,
    count(*) filter (where e.result_status <> 'ok')::int as failed_count,
    count(distinct nullif(e.user_id, '')) filter (where e.result_status = 'ok')::int as unique_users,
    count(distinct nullif(e.session_id, '')) filter (where e.result_status = 'ok')::int as unique_sessions,
    count(*) filter (where e.gemini_calls is not null)::int as metered_count,
    coalesce(sum(e.gemini_prompt_tokens), 0)::bigint as prompt_tokens,
    coalesce(sum(e.gemini_output_tokens), 0)::bigint as output_tokens,
    coalesce(sum(e.gemini_thought_tokens), 0)::bigint as thought_tokens
  from public.app_qa_search_events e
  where (p_since is null or e.created_at >= p_since)
    and (p_until is null or e.created_at < p_until)
  group by 1, 2
  order by 1, 2;
$$;

-- 期間全体の利用者数（週ごとの合算では重複するため別に出す）
create or replace function public.qa_usage_period_users(
  p_since timestamptz default null,
  p_until timestamptz default null
)
returns integer
language sql
stable
set search_path = public
as $$
  select count(distinct nullif(user_id, ''))::int
  from public.app_qa_search_events
  where result_status = 'ok'
    and (p_since is null or created_at >= p_since)
    and (p_until is null or created_at < p_until);
$$;

revoke all on function public.qa_usage_weekly(timestamptz, timestamptz) from public, anon, authenticated;
revoke all on function public.qa_usage_period_users(timestamptz, timestamptz) from public, anon, authenticated;
grant execute on function public.qa_usage_weekly(timestamptz, timestamptz) to service_role;
grant execute on function public.qa_usage_period_users(timestamptz, timestamptz) to service_role;
