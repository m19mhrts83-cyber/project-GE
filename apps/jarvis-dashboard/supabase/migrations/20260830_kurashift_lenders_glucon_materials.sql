-- 融資アプローチ先・銀行別検討材料（jarvis-dashboard）
-- 正本シード: config/kurashift_lenders_approach.yaml
-- 適用: scripts/jarvis_supabase_apply_sql.py 本ファイル

create table if not exists public.kurashift_lenders (
  id text primary key,
  code text,
  name text not null,
  display_name text,
  category text not null default 'bank',
  -- yes | maybe | no | watch | deferred
  approach text not null default 'yes',
  case_report boolean not null default false,
  approach_order int,
  matsuno_notes text,
  store_page_label text,
  region_tags text[] not null default '{}',
  active boolean not null default true,
  source_xlsx text,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists kurashift_lenders_approach_idx
  on public.kurashift_lenders (approach, category);

create table if not exists public.kurashift_lender_intel (
  id uuid primary key default gen_random_uuid(),
  lender_id text not null references public.kurashift_lenders(id) on delete cascade,
  -- seminar-aligned fields (STEP3)
  kind text,
  income_requirement text,
  specialty text,
  rate_notes text,
  full_loan_notes text,
  partner_realtors text,
  approach_order_hint text,
  summary text not null default '',
  source_kind text not null default 'manual',
  -- manual | xlsx | seminar | kamiooya_qa | onedrive | grok
  source_ref text,
  source_excerpt text,
  observed_on date,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists kurashift_lender_intel_lender_idx
  on public.kurashift_lender_intel (lender_id, updated_at desc);

-- Grok / Drive 由来のグルコン活動・成果材料
create table if not exists public.glucon_material_items (
  id uuid primary key default gen_random_uuid(),
  period_key text,
  kind text not null default 'activity',
  -- activity | result | either
  title text not null,
  body text not null default '',
  source text not null default 'grok_drive',
  -- grok_drive | hawk | bucho | manual
  drive_path text,
  tags text[] not null default '{}',
  for_result boolean not null default false,
  status text not null default 'pending',
  -- pending | used | skipped
  used_in_period_key text,
  recorded_at date,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists glucon_material_items_status_idx
  on public.glucon_material_items (status, period_key, kind);

alter table public.kurashift_lenders enable row level security;
alter table public.kurashift_lender_intel enable row level security;
alter table public.glucon_material_items enable row level security;

drop policy if exists kurashift_lenders_auth_all on public.kurashift_lenders;
create policy kurashift_lenders_auth_all on public.kurashift_lenders
  for all to authenticated using (true) with check (true);

drop policy if exists kurashift_lender_intel_auth_all on public.kurashift_lender_intel;
create policy kurashift_lender_intel_auth_all on public.kurashift_lender_intel
  for all to authenticated using (true) with check (true);

drop policy if exists glucon_material_items_auth_all on public.glucon_material_items;
create policy glucon_material_items_auth_all on public.glucon_material_items
  for all to authenticated using (true) with check (true);

grant select, insert, update, delete on public.kurashift_lenders to authenticated, service_role;
grant select, insert, update, delete on public.kurashift_lender_intel to authenticated, service_role;
grant select, insert, update, delete on public.glucon_material_items to authenticated, service_role;
