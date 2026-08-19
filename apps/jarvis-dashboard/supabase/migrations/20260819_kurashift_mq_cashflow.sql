-- MQ 資金繰り表: 起点設定・取引上書き・分類学習ルール

-- 起点・初期残高（法人設立月など）
create table if not exists public.kurashift_mq_cashflow_settings (
  id uuid primary key default gen_random_uuid(),
  business_line text not null default 'realestate'
    check (business_line in ('realestate', 'ai')),
  entity text not null
    check (entity in ('personal', 'corporate')),
  origin_month date not null,
  initial_cash_man numeric not null,
  tax_accrual_month text not null default 'december'
    check (tax_accrual_month in ('december', 'payment')),
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_line, entity)
);

-- 取引単位の資金繰り列上書き（Step 2 / P7）
create table if not exists public.kurashift_mq_cashflow_txn_overrides (
  id uuid primary key default gen_random_uuid(),
  txn_id bigint not null
    references public.kurashift_finance_transactions(id) on delete cascade,
  business_line text not null default 'realestate'
    check (business_line in ('realestate', 'ai')),
  cashflow_column text not null,
  note text,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (txn_id, business_line)
);

create index if not exists kurashift_mq_cashflow_txn_overrides_col_idx
  on public.kurashift_mq_cashflow_txn_overrides (business_line, cashflow_column);

-- 分類学習ルール（P8: 一度直した科目は次回以降同じ列へ）
create table if not exists public.kurashift_mq_cashflow_classify_rules (
  id uuid primary key default gen_random_uuid(),
  business_line text not null default 'realestate'
    check (business_line in ('realestate', 'ai')),
  entity_match text not null default ''
    check (entity_match in ('', 'personal', 'corporate')),
  category_match text not null default '',
  subcategory_match text not null default '',
  cashflow_column text not null,
  source_txn_id bigint
    references public.kurashift_finance_transactions(id) on delete set null,
  note text,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_line, entity_match, category_match, subcategory_match)
);

create index if not exists kurashift_mq_cashflow_classify_rules_lookup_idx
  on public.kurashift_mq_cashflow_classify_rules (
    business_line, entity_match, category_match, subcategory_match
  );

-- 法人設立 2025-01 · 資本金10万円
insert into public.kurashift_mq_cashflow_settings
  (business_line, entity, origin_month, initial_cash_man, note)
select
  'realestate', 'corporate', '2025-01-01'::date, 10,
  '法人設立・資本金10万円（万円単位）'
where not exists (
  select 1 from public.kurashift_mq_cashflow_settings
  where business_line = 'realestate' and entity = 'corporate'
);

do $$
declare
  t text;
begin
  foreach t in array array[
    'kurashift_mq_cashflow_settings',
    'kurashift_mq_cashflow_txn_overrides',
    'kurashift_mq_cashflow_classify_rules'
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
