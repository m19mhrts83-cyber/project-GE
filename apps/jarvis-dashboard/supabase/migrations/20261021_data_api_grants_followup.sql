-- Data API 明示 GRANT follow-up（2026-10-30 前チェック）
-- 20260926 一括 GRANT 以降に増えた表を reset 耐性のため明示。
-- 参考: https://github.com/orgs/supabase/discussions/45329
-- チェックリスト: docs/Supabase_Data_API_明示GRANT_チェックリスト_20261021.md

-- LINE OA webhook イベント（authenticated 可）
do $g$
begin
  if to_regclass('public.line_oa_events') is not null then
    execute 'grant select, insert, update, delete on table public.line_oa_events to authenticated, service_role';
    if to_regclass('public.line_oa_events_id_seq') is not null then
      execute 'grant usage, select on sequence public.line_oa_events_id_seq to authenticated, service_role';
    end if;
  end if;
end
$g$;

-- 為替日次（UI は select、書込は service_role）
do $g$
begin
  if to_regclass('public.yen_rate_daily') is not null then
    execute 'grant select on table public.yen_rate_daily to authenticated';
    execute 'grant select, insert, update, delete on table public.yen_rate_daily to service_role';
  end if;
end
$g$;

-- WeStudy 文字起こし突合（サーバ専用・authenticated に付けない）
do $g$
begin
  if to_regclass('public.westudy_transcript_compare') is not null then
    execute 'revoke all on table public.westudy_transcript_compare from anon, authenticated';
    execute 'grant select, insert, update, delete on table public.westudy_transcript_compare to service_role';
    if to_regclass('public.westudy_transcript_compare_id_seq') is not null then
      execute 'grant usage, select on sequence public.westudy_transcript_compare_id_seq to service_role';
    end if;
  end if;
end
$g$;

-- 以降の新規表でも sequences 一括は安全（既存は idempotent）
grant usage, select on all sequences in schema public to authenticated, service_role;
