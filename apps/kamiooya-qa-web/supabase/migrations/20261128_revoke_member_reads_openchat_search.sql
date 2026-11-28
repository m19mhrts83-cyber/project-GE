-- AIナビの記録（オプチャ記録・検索記録）は、サーバー（service_role）だけが読む（2026-11-28）。
-- 画面・Edge Functions は service_role で読むので、ログインした人（authenticated）・anon の読み取りと関数の実行は使っていない。
-- 何度当てても同じ結果になる。表・関数が無い環境でも止まらない。
do $$
begin
  if to_regclass('public.line_openchat_logs') is not null then
    drop policy if exists line_openchat_logs_auth_select on public.line_openchat_logs;
    revoke all on table public.line_openchat_logs from public, anon, authenticated;
    grant select, insert, update, delete on table public.line_openchat_logs to service_role;
  end if;
  if to_regclass('public.app_qa_search_events') is not null then
    revoke all on table public.app_qa_search_events from public, anon, authenticated;
    grant select, insert, update, delete on table public.app_qa_search_events to service_role;
  end if;
  if to_regclass('public.app_qa_search_mode_daily') is not null then
    revoke all on table public.app_qa_search_mode_daily from public, anon, authenticated;
    grant select on table public.app_qa_search_mode_daily to service_role;
  end if;
  if to_regprocedure('public.search_openchat_keyword(text,integer)') is not null then
    revoke all on function public.search_openchat_keyword(text, int) from public, anon, authenticated;
    grant execute on function public.search_openchat_keyword(text, int) to service_role;
  end if;
  if to_regprocedure('public.match_openchat_semantic(extensions.vector,double precision,integer)') is not null then
    revoke all on function public.match_openchat_semantic(extensions.vector, float, int) from public, anon, authenticated;
    grant execute on function public.match_openchat_semantic(extensions.vector, float, int) to service_role;
  end if;
end $$;

-- 確かめ（読むだけ）:
-- select grantee, privilege_type from information_schema.role_table_grants
--  where table_schema='public' and table_name in ('line_openchat_logs','app_qa_search_events','app_qa_search_mode_daily')
--    and grantee in ('anon','authenticated');   -- 0 行
-- select p.proname, has_function_privilege('authenticated', p.oid, 'execute') from pg_proc p
--  where p.proname in ('search_openchat_keyword','match_openchat_semantic');  -- どちらも false
-- select policyname from pg_policies where tablename='line_openchat_logs' and 'authenticated' = any(roles);  -- 0 行
