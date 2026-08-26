-- 業者生存確認列 + S4 修繕 / S9 管理会社テーブル
-- jarvis-dashboard (idkdqneutpvkhxhpjtgc)

-- === S2 地場業者: alive_* ===
alter table public.kurashift_re_vendors
  add column if not exists alive_checked_at date,
  add column if not exists alive_status text not null default 'unknown',
  add column if not exists alive_method text,
  add column if not exists alive_note text,
  add column if not exists alive_due_days integer not null default 180;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'kurashift_re_vendors_alive_status_check'
  ) then
    alter table public.kurashift_re_vendors
      add constraint kurashift_re_vendors_alive_status_check
      check (alive_status in ('unknown','ok','fail','stale'));
  end if;
end $$;

create index if not exists kurashift_re_vendors_alive_idx
  on public.kurashift_re_vendors (alive_status, alive_checked_at desc nulls last);

-- === S9 管理会社開拓 ===
create table if not exists public.kurashift_re_mgmt_vendors (
  id text primary key,
  name text not null,
  area text,
  prefecture text,
  city text,
  station text,
  url text,
  contact_url text,
  channel text not null default 'web_form',
  contact_email text,
  phone text,
  status text not null default 'pending'
    check (status in ('pending','discovered','contacted','replied','skip','invalid')),
  source text,
  discovered_at date,
  contacted_at date,
  replied_at date,
  last_result text,
  notes text,
  services jsonb not null default '{}'::jsonb,
  property_area text,
  alive_checked_at date,
  alive_status text not null default 'unknown'
    check (alive_status in ('unknown','ok','fail','stale')),
  alive_method text,
  alive_note text,
  alive_due_days integer not null default 180,
  synced_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists kurashift_re_mgmt_vendors_status_idx
  on public.kurashift_re_mgmt_vendors (status, contacted_at desc nulls last);

create index if not exists kurashift_re_mgmt_vendors_alive_idx
  on public.kurashift_re_mgmt_vendors (alive_status, alive_checked_at desc nulls last);

alter table public.kurashift_re_mgmt_vendors enable row level security;

drop policy if exists kurashift_re_mgmt_vendors_auth_all on public.kurashift_re_mgmt_vendors;
create policy kurashift_re_mgmt_vendors_auth_all
  on public.kurashift_re_mgmt_vendors
  for all to authenticated
  using (true)
  with check (true);

-- === S4 修繕業者 ===
create table if not exists public.kurashift_re_repair_vendors (
  id text primary key,
  name text not null,
  trade text,
  area text,
  prefecture text,
  city text,
  url text,
  contact_url text,
  channel text not null default 'phone',
  contact_email text,
  phone text,
  status text not null default 'pending'
    check (status in ('pending','discovered','contacted','replied','skip','invalid')),
  source text,
  sole_proprietor_score text,
  discovered_at date,
  contacted_at date,
  replied_at date,
  last_result text,
  notes text,
  alive_checked_at date,
  alive_status text not null default 'unknown'
    check (alive_status in ('unknown','ok','fail','stale')),
  alive_method text,
  alive_note text,
  alive_due_days integer not null default 90,
  synced_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists kurashift_re_repair_vendors_status_idx
  on public.kurashift_re_repair_vendors (status, trade, contacted_at desc nulls last);

create index if not exists kurashift_re_repair_vendors_alive_idx
  on public.kurashift_re_repair_vendors (alive_status, alive_checked_at desc nulls last);

alter table public.kurashift_re_repair_vendors enable row level security;

drop policy if exists kurashift_re_repair_vendors_auth_all on public.kurashift_re_repair_vendors;
create policy kurashift_re_repair_vendors_auth_all
  on public.kurashift_re_repair_vendors
  for all to authenticated
  using (true)
  with check (true);
