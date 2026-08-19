-- 家計キヨサキB/S 月次スナップ（Phase C）
-- payload: HouseholdBsView 相当の JSON（行配列・合計・mqSlices）

create table if not exists public.kurashift_household_bs_snapshots (
  id uuid primary key default gen_random_uuid(),
  as_of_month text not null check (as_of_month ~ '^\d{4}-\d{2}$'),
  fiscal_year integer not null,
  payload jsonb not null default '{}'::jsonb,
  source text not null default 'jarvis'
    check (source in ('manual', 'jarvis', 'import')),
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (as_of_month, fiscal_year)
);

create index if not exists kurashift_household_bs_snapshots_month_idx
  on public.kurashift_household_bs_snapshots (as_of_month desc);

create index if not exists kurashift_household_bs_snapshots_year_idx
  on public.kurashift_household_bs_snapshots (fiscal_year desc);

alter table public.kurashift_household_bs_snapshots enable row level security;

drop policy if exists kurashift_household_bs_snapshots_auth_all
  on public.kurashift_household_bs_snapshots;
create policy kurashift_household_bs_snapshots_auth_all
  on public.kurashift_household_bs_snapshots
  for all to authenticated
  using (true)
  with check (true);

comment on table public.kurashift_household_bs_snapshots is
  '家計B/S 月次スナップ。live compose より優先表示。欠損は NULL のまま。';
