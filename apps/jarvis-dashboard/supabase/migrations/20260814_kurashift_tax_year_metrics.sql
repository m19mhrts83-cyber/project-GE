-- 確定申告の年度KPI（個人＝暦年／法人＝5月期）。申告結果の正。Zaim気配とは別。

create table if not exists public.kurashift_tax_year_metrics (
  id uuid primary key default gen_random_uuid(),
  scope text not null
    check (scope in ('personal', 'corporate')),
  fiscal_year int not null,
  filing_status text
    check (
      filing_status is null
      or filing_status in ('draft', 'filed', 'amended', 'unknown')
    ),
  filed_on date,
  note text,
  source text not null default 'manual'
    check (source in ('manual', 'jarvis', 'import')),
  -- 個人
  taxable_income_jpy numeric,
  income_tax_jpy numeric,
  refund_or_pay text
    check (
      refund_or_pay is null
      or refund_or_pay in ('refund', 'pay', 'zero')
    ),
  -- 法人
  revenue_jpy numeric,
  ordinary_income_jpy numeric,
  corporate_tax_jpy numeric,
  tax_payable_jpy numeric,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (scope, fiscal_year)
);

create index if not exists kurashift_tax_year_metrics_scope_year_idx
  on public.kurashift_tax_year_metrics (scope, fiscal_year desc);

alter table public.kurashift_tax_year_metrics enable row level security;

drop policy if exists kurashift_tax_year_metrics_auth_all
  on public.kurashift_tax_year_metrics;
create policy kurashift_tax_year_metrics_auth_all
  on public.kurashift_tax_year_metrics
  for all to authenticated
  using (true)
  with check (true);
