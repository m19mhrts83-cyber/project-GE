-- 業者開拓投影 + 物件候補判断履歴

create table if not exists public.kurashift_re_vendors (
  id text primary key,
  name text not null,
  area text,
  prefecture text,
  city text,
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
  ops_contacted_at date,
  last_result text,
  notes text,
  synced_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists kurashift_re_vendors_status_idx
  on public.kurashift_re_vendors (status, contacted_at desc nulls last);

alter table public.kurashift_re_vendors enable row level security;

drop policy if exists kurashift_re_vendors_auth_all on public.kurashift_re_vendors;
create policy kurashift_re_vendors_auth_all
  on public.kurashift_re_vendors
  for all to authenticated
  using (true)
  with check (true);

create table if not exists public.kurashift_re_deal_events (
  id uuid primary key default gen_random_uuid(),
  deal_id uuid not null references public.kurashift_re_deals(id) on delete cascade,
  event_type text not null
    check (event_type in (
      'created','status_change','inquiry_sent','inquiry_reply',
      'grok_applied','review_confirm','review_pass','note'
    )),
  from_status text,
  to_status text,
  actor text not null default 'user',
  summary text not null default '',
  payload jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now()
);

create index if not exists kurashift_re_deal_events_deal_idx
  on public.kurashift_re_deal_events (deal_id, occurred_at desc);

alter table public.kurashift_re_deal_events enable row level security;

drop policy if exists kurashift_re_deal_events_auth_all on public.kurashift_re_deal_events;
create policy kurashift_re_deal_events_auth_all
  on public.kurashift_re_deal_events
  for all to authenticated
  using (true)
  with check (true);
