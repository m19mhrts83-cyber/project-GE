# Supabase Data API — 明示 GRANT チェックリスト（2026-10-30）

公式変更: **2026-10-30** 以降、既存プロジェクトでも `public` の**新規テーブル**に Data API（PostgREST / `supabase-js`）向けの自動 GRANT が付かない。  
既存テーブルの権限はそのまま。新規 CREATE だけ明示 `GRANT` が必須。

- 公式ディスカッション: https://github.com/orgs/supabase/discussions/45329
- 復習: https://claude-code-supabase-fukushu.vercel.app/
- ルール: `.cursor/rules/jarvis-supabase-free-one-project.mdc`

## 影響サマリ（このリポ）

| プロジェクト | ref | 既存表 | 10/30 以降の新規表 |
|---|---|---|---|
| **jarvis-dashboard** | `idkdqneutpvkhxhpjtgc` | 監査済・Data API 到達可（下記） | CREATE と同 migration に GRANT |
| **kamiooya-qa**（prompt-share 含む） | `mwubzgefkkjjbingrmqu` | 全表 `service_role` 明示済 | 同上（主に `service_role`） |

**既存テーブルへの緊急作業は不要。** 残作業は「今後の migration 習慣」と reset 耐性の明示 GRANT。

## 移行前チェックリスト

### A. 既存（〜10/29）— 完了確認

- [x] jarvis-dashboard: 公開表は `authenticated` / `service_role` で SELECT 可能（監査 2026-10-21）
- [x] jarvis-dashboard: `westudy_transcript_compare` は意図どおり **service_role のみ**（UI 直読しない）
- [x] kamiooya-qa: 全 public 表に `service_role` DML（prompt_* / line_openchat_logs 含む）
- [x] 一括明示: `apps/jarvis-dashboard/supabase/migrations/20260926_data_api_explicit_grants.sql`
- [x] follow-up: `apps/jarvis-dashboard/supabase/migrations/20261021_data_api_grants_followup.sql`
- [x] jarvis README に定型 GRANT 記載

### B. 10/30 以降の新規テーブル（毎回）

CREATE と同じ migration / schema 追記に必ず含める:

```sql
create table if not exists public.your_table ( ... );
alter table public.your_table enable row level security;
-- policy ...

-- jarvis-dashboard（ログイン後 UI）
grant select, insert, update, delete on table public.your_table
  to authenticated, service_role;
-- serial / identity があるとき
grant usage, select on sequence public.your_table_id_seq
  to authenticated, service_role;

-- kamiooya-qa / prompt-share（サーバ専用が多い）
-- grant select, insert, update, delete on table public.your_table to service_role;
-- （anon / authenticated は付けない。必要なときだけ最小権限）
```

チェック:

- [ ] CREATE と同一ファイルに `grant …`
- [ ] `anon` を安易に付けていない（必要なら RLS + 最小権限）
- [ ] identity / serial なら sequence の `usage, select`
- [ ] jarvis-dashboard なら `20260926` 一括リストへ表名追記（任意・reset 耐性）

### C. 適用コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a

# jarvis-dashboard
~/selenium_env/venv/bin/python scripts/jarvis_supabase_apply_sql.py \
  apps/jarvis-dashboard/supabase/migrations/20260926_data_api_explicit_grants.sql
~/selenium_env/venv/bin/python scripts/jarvis_supabase_apply_sql.py \
  apps/jarvis-dashboard/supabase/migrations/20261021_data_api_grants_followup.sql

# kamiooya-qa（必要時 --ref）
~/selenium_env/venv/bin/python scripts/jarvis_supabase_apply_sql.py \
  --ref mwubzgefkkjjbingrmqu \
  apps/kamiooya-qa-web/supabase/migrations/20261021_data_api_grants_verify.sql
```

### D. 監査 SQL（Dashboard SQL Editor または apply_sql）

```sql
select c.relname as table_name,
  has_table_privilege('authenticated', c.oid, 'select') as auth_select,
  has_table_privilege('service_role', c.oid, 'select') as svc_select,
  has_table_privilege('anon', c.oid, 'select') as anon_select
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by c.relname;
```

期待:

- jarvis-dashboard: ほぼすべて `auth_select` / `svc_select` = true（例外: `westudy_transcript_compare` は svc のみ）
- kamiooya-qa: `svc_select` = true、`auth_select` / `anon_select` = false が既定

## やらないこと

- 10/30 前に default privileges を勝手に剥がして「予行」する（既存アプリを壊しうる）
- Free で第3プロジェクトを作る
- `anon` に全表 GRANT（RLS 前提でも最小権限）

## 監査メモ（2026-10-21）

| PJ | 結果 |
|---|---|
| jarvis-dashboard | 90 表相当。`westudy_transcript_compare` のみ intentional に auth なし。他は auth+svc OK |
| kamiooya-qa | 13 表。すべて service_role OK。prompt-share 3 表も同 PJ |
| default ACL | jarvis はまだ自動 GRANT 寄り。kamiooya の postgres 側は既に anon/auth の DML が狭い。10/30 後は両 PJ とも「CREATE に GRANT 必須」で揃う |
| 本番適用 | jarvis-dashboard に `20261021_data_api_grants_followup` 適用済（idempotent） |
