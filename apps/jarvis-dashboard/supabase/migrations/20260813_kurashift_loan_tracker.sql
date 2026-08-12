-- 借入残高トラッカーの読取投影（正本は loan-tracker Drive。ここへは書かない）
-- RLS: 既存 kurashift_* と同様、アプリ側（authenticated / service_role）で制御

create table if not exists public.kurashift_loan_tracker_loans (
  id text primary key,
  name text,
  lender text,
  category_major text,
  tags text[] not null default '{}',
  principal_jpy numeric,
  balance_jpy numeric,
  monthly_payment_jpy numeric,
  annual_payment_jpy numeric,
  rate_pct numeric,
  rate_type text,
  start_date date,
  payoff_date date,
  payload jsonb not null default '{}'::jsonb,
  synced_at timestamptz not null default now()
);

create index if not exists kurashift_loan_tracker_loans_major_idx
  on public.kurashift_loan_tracker_loans (category_major, balance_jpy desc);
