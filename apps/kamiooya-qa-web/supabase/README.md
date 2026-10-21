# kamiooya-qa / Supabase

プロジェクト: `kamiooya-qa`（運営提供・引き渡し対象。Free 2本のうちの1つ）  
ref: `mwubzgefkkjjbingrmqu`

prompt-share（`prompts` / `prompt_groups` / `prompt_usage_events`）も**このプロジェクト**に載せる。

## 2026-10-30: Data API の明示 GRANT（必須）

**既存テーブルは現状の GRANT のまま動く。** 同日以降の `public` 新規テーブルは Data API 用に明示 `GRANT` が必要。

### 新規テーブル時の定型（この PJ）

```sql
create table if not exists public.your_table ( ... );
alter table public.your_table enable row level security;

-- サーバ（service_role）本線。anon / authenticated は原則付けない
grant select, insert, update, delete on table public.your_table to service_role;
grant usage, select on sequence public.your_table_id_seq to service_role;
```

クライアントから読む必要があるときだけ、最小権限 + RLS を足す。

### 検証 SQL

`migrations/20261021_data_api_grants_verify.sql`（読み取り専用の監査クエリ）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_supabase_apply_sql.py \
  --ref mwubzgefkkjjbingrmqu \
  apps/kamiooya-qa-web/supabase/migrations/20261021_data_api_grants_verify.sql
```

チェックリスト正本: `docs/Supabase_Data_API_明示GRANT_チェックリスト_20261021.md`  
公式: https://github.com/orgs/supabase/discussions/45329
