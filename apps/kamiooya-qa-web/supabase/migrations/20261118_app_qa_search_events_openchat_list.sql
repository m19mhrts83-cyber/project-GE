-- 検索の利用記録（app_qa_search_events）に、LINEオプチャ一覧の閲覧（search_mode='openchat_list'）を保存できるようにする（2026-11-18）。
-- これまで入力チェックが normal / semantic だけを許していたため、一覧・スレッド・ID指定の記録はすべて保存に失敗していた。
-- 一覧の閲覧は「質問」ではないので、利用者数・週次集計・質問テーマの集計には今までどおり入れない（normal / semantic だけを数える）。
alter table public.app_qa_search_events drop constraint if exists app_qa_search_events_search_mode_check;
alter table public.app_qa_search_events add constraint app_qa_search_events_search_mode_check
  check (search_mode = any (array['normal'::text, 'semantic'::text, 'openchat_list'::text]));

create or replace function public.qa_usage_weekly(p_since timestamptz default null, p_until timestamptz default null)
returns table(week_start_jst date, search_mode text, ok_count integer, failed_count integer, unique_users integer, unique_sessions integer, metered_count integer, prompt_tokens bigint, output_tokens bigint, thought_tokens bigint)
language sql stable set search_path to 'public'
as $function$
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
    and e.search_mode in ('normal', 'semantic')
  group by 1, 2
  order by 1, 2;
$function$;

create or replace function public.qa_usage_period_users(p_since timestamptz default null, p_until timestamptz default null)
returns integer
language sql stable set search_path to 'public'
as $function$
  select count(distinct nullif(user_id, ''))::int
  from public.app_qa_search_events
  where result_status = 'ok'
    and search_mode in ('normal', 'semantic')
    and (p_since is null or created_at >= p_since)
    and (p_until is null or created_at < p_until);
$function$;

-- 質問テーマの集計（長い関数なので、質問ログを読む1行だけを差し替える。想定と違う形なら止める）
do $$
declare
  d text := pg_get_functiondef('public.qa_theme_source_digest(integer)'::regprocedure);
  old_line constant text := $q$where created_at >= since.t and coalesce(btrim(query_text),'') <> ''$q$;
  new_line constant text := $q$where created_at >= since.t and coalesce(btrim(query_text),'') <> '' and search_mode in ('normal','semantic')$q$;
begin
  if position(new_line in d) > 0 then return; end if;
  if (length(d) - length(replace(d, old_line, ''))) / length(old_line) <> 1 then
    raise exception 'qa_theme_source_digest: unexpected definition';
  end if;
  execute replace(d, old_line, new_line);
end $$;
