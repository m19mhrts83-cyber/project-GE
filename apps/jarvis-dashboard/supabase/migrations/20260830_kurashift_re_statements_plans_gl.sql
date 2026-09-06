-- Kneesbee / 事業計画 → 法人 BS・PL 正本テーブル
-- jarvis-dashboard のみ。kamiooya-qa には作らない。

-- 期次の確定決算スナップ（税理士提出・R8等）
create table if not exists public.kurashift_re_statements (
  id uuid primary key default gen_random_uuid(),
  entity text not null check (entity in ('personal', 'corporate')),
  fiscal_year int not null,
  -- 例: 2025-06-01 〜 2026-05-31 → label 'R8' / period_end 2026-05-31
  period_start date,
  period_end date not null,
  label text,
  source text not null default 'manual'
    check (source in (
      'manual', 'kneesbee_r8', 'kneesbee_r7', 'mykomon',
      'notion_meeting', 'import', 'jarvis'
    )),
  -- PL（円）。NULL=未確定
  revenue_jpy numeric,
  operating_profit_jpy numeric,
  pretax_profit_jpy numeric,
  tax_jpy numeric,
  net_income_jpy numeric,
  -- BS（円）
  cash_jpy numeric,
  total_assets_jpy numeric,
  bank_loan_jpy numeric,
  officer_loan_jpy numeric,
  capital_jpy numeric,
  retained_earnings_jpy numeric,
  -- 拡張（科目内訳・メモ）
  pl_json jsonb not null default '{}'::jsonb,
  bs_json jsonb not null default '{}'::jsonb,
  reconcile_notes text,
  evidence_path text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (entity, period_end, source)
);

create index if not exists kurashift_re_statements_entity_fy_idx
  on public.kurashift_re_statements (entity, fiscal_year desc);

alter table public.kurashift_re_statements enable row level security;
drop policy if exists kurashift_re_statements_auth_all on public.kurashift_re_statements;
create policy kurashift_re_statements_auth_all
  on public.kurashift_re_statements for all to authenticated
  using (true) with check (true);

comment on table public.kurashift_re_statements is
  '不動産事業の期次確定決算スナップ。法人は Kneesbee/MyKomon 正本。合算はアプリ側。';

-- 事業計画（期次見込）
create table if not exists public.kurashift_re_annual_plans (
  id uuid primary key default gen_random_uuid(),
  entity text not null check (entity in ('personal', 'corporate')),
  fiscal_year int not null,
  label text,
  source text not null default 'manual'
    check (source in (
      'manual', 'mykomon', 'kneesbee', 'notion_meeting',
      'numbers', 'revised', 'jarvis'
    )),
  plan_json jsonb not null default '{}'::jsonb,
  -- 便利列（円）— plan_json と同期してよい
  revenue_jpy numeric,
  operating_profit_jpy numeric,
  pretax_profit_jpy numeric,
  cash_flow_jpy numeric,
  occupancy_pct numeric,
  notes text,
  evidence_path text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (entity, fiscal_year, source, label)
);

create index if not exists kurashift_re_annual_plans_entity_fy_idx
  on public.kurashift_re_annual_plans (entity, fiscal_year);

alter table public.kurashift_re_annual_plans enable row level security;
drop policy if exists kurashift_re_annual_plans_auth_all on public.kurashift_re_annual_plans;
create policy kurashift_re_annual_plans_auth_all
  on public.kurashift_re_annual_plans for all to authenticated
  using (true) with check (true);

comment on table public.kurashift_re_annual_plans is
  '事業計画の期次見込。Notion 8/28・MyKomon 事業計画を格納。';

-- 月次実績（将来: 元帳集計／当面手載せ）
create table if not exists public.kurashift_re_actuals (
  id uuid primary key default gen_random_uuid(),
  entity text not null check (entity in ('personal', 'corporate')),
  fiscal_year int not null,
  month int not null check (month between 1 and 12),
  income_jpy numeric,
  expense_jpy numeric,
  cf_jpy numeric,
  breakdown_json jsonb not null default '{}'::jsonb,
  source text not null default 'manual'
    check (source in ('manual', 'zaim', 'mykomon', 'gl', 'jarvis')),
  ingested_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (entity, fiscal_year, month, source)
);

create index if not exists kurashift_re_actuals_entity_ym_idx
  on public.kurashift_re_actuals (entity, fiscal_year, month);

alter table public.kurashift_re_actuals enable row level security;
drop policy if exists kurashift_re_actuals_auth_all on public.kurashift_re_actuals;
create policy kurashift_re_actuals_auth_all
  on public.kurashift_re_actuals for all to authenticated
  using (true) with check (true);

-- 総勘定元帳明細
create table if not exists public.kurashift_re_gl_lines (
  id uuid primary key default gen_random_uuid(),
  entity text not null check (entity in ('personal', 'corporate')),
  fiscal_year int,
  txn_date date,
  account_code text,
  account_name text not null,
  description text,
  counterparty text,
  debit_jpy numeric,
  credit_jpy numeric,
  amount_jpy numeric,
  source_file text,
  source text not null default 'mykomon'
    check (source in ('mykomon', 'import', 'manual', 'jarvis')),
  row_fingerprint text,
  created_at timestamptz not null default now(),
  unique (entity, row_fingerprint)
);

create index if not exists kurashift_re_gl_lines_account_idx
  on public.kurashift_re_gl_lines (entity, account_name, txn_date);

create index if not exists kurashift_re_gl_lines_fy_idx
  on public.kurashift_re_gl_lines (entity, fiscal_year);

alter table public.kurashift_re_gl_lines enable row level security;
drop policy if exists kurashift_re_gl_lines_auth_all on public.kurashift_re_gl_lines;
create policy kurashift_re_gl_lines_auth_all
  on public.kurashift_re_gl_lines for all to authenticated
  using (true) with check (true);

comment on table public.kurashift_re_gl_lines is
  '総勘定元帳明細。MyKomon/Excel 取込。科目レベル突合用。';
