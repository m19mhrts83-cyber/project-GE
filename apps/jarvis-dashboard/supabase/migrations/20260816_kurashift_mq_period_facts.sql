-- MQ会計評価 Phase B: 期次実績（手入力）facts
-- jarvis-dashboard のみ。kamiooya-qa には作らない。

create table if not exists public.kurashift_mq_period_facts (
  id uuid primary key default gen_random_uuid(),
  business_line text not null
    check (business_line in ('realestate', 'ai')),
  entity text not null
    check (entity in ('personal', 'corporate')),
  period_month date not null,
  scenario_kind text not null default 'actual'
    check (scenario_kind in ('actual', 'plan')),
  plan_variant_id text not null default '',
  q numeric,
  pq numeric not null default 0,
  vq numeric not null default 0,
  -- f: すでに月額の固定費（利息・定額管理など）
  f numeric not null default 0,
  -- f_annual: 年額で払う固定費（固都税・年払保険など）。月次評価では ÷12 按分
  f_annual numeric not null default 0,
  cash_in numeric,
  cash_out numeric,
  cash_end numeric,
  depreciation_jpy numeric,
  note text,
  source text not null default 'manual'
    check (source in ('manual', 'jarvis', 'import')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_line, entity, period_month, scenario_kind, plan_variant_id)
);

create index if not exists kurashift_mq_period_facts_period_idx
  on public.kurashift_mq_period_facts (period_month desc);

create index if not exists kurashift_mq_period_facts_line_entity_idx
  on public.kurashift_mq_period_facts (business_line, entity, period_month desc);

alter table public.kurashift_mq_period_facts enable row level security;

drop policy if exists kurashift_mq_period_facts_auth_all
  on public.kurashift_mq_period_facts;
create policy kurashift_mq_period_facts_auth_all
  on public.kurashift_mq_period_facts
  for all to authenticated
  using (true)
  with check (true);

comment on table public.kurashift_mq_period_facts is
  'MQ会計評価。実績=月次（f_annualは月表示で÷12）。計画=年次行（scenario=plan）。合算はアプリ合成。';
