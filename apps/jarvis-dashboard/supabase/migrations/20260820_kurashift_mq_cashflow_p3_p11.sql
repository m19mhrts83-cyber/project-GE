-- MQ 資金繰り P3–P11: 期末手入力・処置シミュレーション・投影履歴
-- jarvis-dashboard のみ。kamiooya-qa には作らない。

-- 月次の手動上書き（利息・税金・借入流入）
create table if not exists public.kurashift_mq_cashflow_adjustments (
  id uuid primary key default gen_random_uuid(),
  business_line text not null default 'realestate'
    check (business_line in ('realestate', 'ai')),
  entity text not null
    check (entity in ('personal', 'corporate')),
  period_month date not null,
  field_key text not null,
  amount_man numeric not null,
  source text not null default 'manual'
    check (source in ('manual', 'import', 'simulation')),
  note text,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_line, entity, period_month, field_key)
);

create index if not exists kurashift_mq_cashflow_adjustments_period_idx
  on public.kurashift_mq_cashflow_adjustments (business_line, entity, period_month);

-- 処置シミュレーション（バーチャル流入）
create table if not exists public.kurashift_mq_cashflow_actions (
  id uuid primary key default gen_random_uuid(),
  business_line text not null default 'realestate'
    check (business_line in ('realestate', 'ai')),
  entity text not null
    check (entity in ('personal', 'corporate')),
  period_month date not null,
  action_kind text not null
    check (action_kind in ('officer', 'borrow_st', 'borrow_lt')),
  amount_man numeric not null check (amount_man > 0),
  label text not null default '',
  is_active boolean not null default true,
  sort_order int not null default 0,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists kurashift_mq_cashflow_actions_period_idx
  on public.kurashift_mq_cashflow_actions (business_line, entity, period_month);

-- L1 → L2/L3 反映の監査
create table if not exists public.kurashift_mq_cashflow_projections (
  id uuid primary key default gen_random_uuid(),
  business_line text not null default 'realestate'
    check (business_line in ('realestate', 'ai')),
  entity text not null
    check (entity in ('personal', 'corporate')),
  fiscal_year int not null,
  fact_months int not null default 0,
  skipped_manual int not null default 0,
  bs_applied boolean not null default false,
  note text,
  payload jsonb,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now()
);

create index if not exists kurashift_mq_cashflow_projections_year_idx
  on public.kurashift_mq_cashflow_projections (business_line, entity, fiscal_year desc);

do $$
declare
  t text;
begin
  foreach t in array array[
    'kurashift_mq_cashflow_adjustments',
    'kurashift_mq_cashflow_actions',
    'kurashift_mq_cashflow_projections'
  ]
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists %I_auth_all on public.%I', t, t);
    execute format(
      'create policy %I_auth_all on public.%I for all to authenticated using (true) with check (true)',
      t, t
    );
  end loop;
end $$;

-- facts / B/S の source に資金繰り投影を追加
alter table public.kurashift_mq_period_facts
  drop constraint if exists kurashift_mq_period_facts_source_check;
alter table public.kurashift_mq_period_facts
  add constraint kurashift_mq_period_facts_source_check
  check (source in ('manual', 'jarvis', 'import', 'cashflow'));

alter table public.kurashift_mq_bs_snapshots
  drop constraint if exists kurashift_mq_bs_snapshots_source_check;
alter table public.kurashift_mq_bs_snapshots
  add constraint kurashift_mq_bs_snapshots_source_check
  check (source in ('manual', 'jarvis', 'import', 'cashflow_project'));
