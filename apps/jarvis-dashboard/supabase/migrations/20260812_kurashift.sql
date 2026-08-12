-- KURASHIFT tables (jarvis-dashboard)
-- App: apps/trade-desk (brand KURASHIFT)

create table if not exists public.kurashift_jobs (
  id uuid primary key default gen_random_uuid(),
  job_type text not null,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  title text,
  payload jsonb not null default '{}'::jsonb,
  result jsonb not null default '{}'::jsonb,
  log_text text not null default '',
  artifacts jsonb not null default '[]'::jsonb,
  error_text text,
  created_by text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);

create index if not exists kurashift_jobs_status_created_idx
  on public.kurashift_jobs (status, created_at desc);

create table if not exists public.kurashift_consultations (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text not null default '',
  lane text not null default 'general'
    check (lane in ('general', 'lifeplan', 'theme', 'tax', 'core')),
  decision text,
  status text not null default 'open'
    check (status in ('open', 'decided', 'archived')),
  related_job_id uuid references public.kurashift_jobs(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists kurashift_consultations_lane_created_idx
  on public.kurashift_consultations (lane, created_at desc);

create table if not exists public.kurashift_themes (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  hypothesis text not null default '',
  amount_jpy numeric,
  duration_note text,
  funding_path text,
  status text not null default 'draft'
    check (status in ('draft', 'consulting', 'approved', 'executing', 'closed', 'reviewed')),
  consultation_id uuid references public.kurashift_consultations(id) on delete set null,
  review_note text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists kurashift_themes_status_created_idx
  on public.kurashift_themes (status, created_at desc);

create table if not exists public.kurashift_plan_snapshots (
  id uuid primary key default gen_random_uuid(),
  label text not null,
  fiscal_year int,
  snapshot_at date not null default (current_date),
  metrics jsonb not null default '{}'::jsonb,
  notes text,
  created_at timestamptz not null default now()
);

create index if not exists kurashift_plan_snapshots_year_idx
  on public.kurashift_plan_snapshots (fiscal_year desc, snapshot_at desc);

create table if not exists public.kurashift_tax_cases (
  id uuid primary key default gen_random_uuid(),
  fiscal_year int not null,
  title text not null,
  status text not null default 'draft'
    check (status in ('draft', 'csv_ready', 'registered', 'closed')),
  scope text not null default 'personal'
    check (scope = 'personal'),
  csv_path text,
  notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (fiscal_year, title)
);

create table if not exists public.kurashift_tax_evidence (
  id uuid primary key default gen_random_uuid(),
  tax_case_id uuid references public.kurashift_tax_cases(id) on delete cascade,
  fiscal_year int not null,
  source text not null default 'gmail'
    check (source in ('gmail', 'upload', 'export')),
  doc_kind text not null default 'attachment',
  subject text,
  gmail_message_id text,
  stored_path text not null,
  original_filename text,
  metadata jsonb not null default '{}'::jsonb,
  received_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists kurashift_tax_evidence_year_idx
  on public.kurashift_tax_evidence (fiscal_year desc, created_at desc);

-- portfolio accounts: Chikage / Prudential placeholders
insert into public.portfolio_accounts (id, name, kind, institution, ingest, notes)
values
  ('sony_life_chikage', 'ソニー生命（千景）', 'insurance_sony', 'ソニー生命', 'monthly_form', 'KURASHIFT Core。真治と分けて表示'),
  ('prudential_life', 'プルデンシャル生命（真治）', 'insurance_prudential', 'プルデンシャル生命', 'manual', '少額でも評価に含める'),
  ('prudential_life_chikage', 'プルデンシャル生命（千景）', 'insurance_prudential', 'プルデンシャル生命', 'manual', '少額でも評価に含める'),
  ('bloomo', 'Bloomo', 'robo_bloomo', 'Bloomo', 'web_playwright', '固定／動的スリーブ。Web正')
on conflict (id) do nothing;

do $$
declare
  t text;
begin
  foreach t in array array[
    'kurashift_jobs', 'kurashift_consultations', 'kurashift_themes',
    'kurashift_plan_snapshots', 'kurashift_tax_cases', 'kurashift_tax_evidence'
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
