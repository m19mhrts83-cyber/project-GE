-- kamiooya-qa: Data API GRANT 監査（読み取り専用）
-- 10/30 以降の新規表は CREATE と同 migration で service_role へ明示 GRANT すること。
-- チェックリスト: docs/Supabase_Data_API_明示GRANT_チェックリスト_20261021.md

select c.relname as table_name,
  has_table_privilege('service_role', c.oid, 'select') as svc_select,
  has_table_privilege('service_role', c.oid, 'insert') as svc_insert,
  has_table_privilege('authenticated', c.oid, 'select') as auth_select,
  has_table_privilege('anon', c.oid, 'select') as anon_select
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by c.relname;
