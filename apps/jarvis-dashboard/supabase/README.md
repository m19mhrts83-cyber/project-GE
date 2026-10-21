# jarvis-dashboard / Supabase

プロジェクト: `jarvis-dashboard`（自分用。Free 2本のうちの1つ）

## 2026-10-30: Data API の明示 GRANT（必須）

Supabase は **2026-10-30** 以降、既存プロジェクトでも `public` の**新規テーブル**に Data API（`supabase-js` / PostgREST）向けの自動 GRANT をしなくなる。

| 対象 | 影響 |
|---|---|
| **既存テーブル** | なし（現状の GRANT のまま動く） |
| **10/30 以降に作る新規テーブル** | `GRANT` 無しだと API が permission denied |
| **migration / db reset / preview** | CREATE と同じ migration に GRANT を書く |

**作成ルール（Cursor 常時）:** `.cursor/rules/jarvis-supabase-data-api-grant.mdc`  
**移行前チェックリスト（正本）:** [`docs/Supabase_Data_API_明示GRANT_チェックリスト_20261021.md`](../../../docs/Supabase_Data_API_明示GRANT_チェックリスト_20261021.md)

### 新規テーブル時の定型（この PJ）

```sql
create table if not exists public.your_table ( ... );
alter table public.your_table enable row level security;
-- policy ...

grant select, insert, update, delete on table public.your_table
  to authenticated, service_role;
-- serial / identity があるとき
grant usage, select on sequence public.your_table_id_seq
  to authenticated, service_role;
```

- **anon には付けない**（ダッシュボードはログイン後の `authenticated` 想定）
- サーバ専用表は `service_role` のみ（例: `westudy_transcript_compare`）
- 一括明示: `migrations/20260926_data_api_explicit_grants.sql`
- follow-up: `migrations/20261021_data_api_grants_followup.sql`
- 公式: https://github.com/orgs/supabase/discussions/45329

### 適用

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_supabase_apply_sql.py \
  apps/jarvis-dashboard/supabase/migrations/20260926_data_api_explicit_grants.sql
~/selenium_env/venv/bin/python scripts/jarvis_supabase_apply_sql.py \
  apps/jarvis-dashboard/supabase/migrations/20261021_data_api_grants_followup.sql
```

`kamiooya-qa` / `prompt-share` の schema はもともと GRANT 付き。新規表でも同様に明示すること（`apps/kamiooya-qa-web/supabase/README.md`）。
