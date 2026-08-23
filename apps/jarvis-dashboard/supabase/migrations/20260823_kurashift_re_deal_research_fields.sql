-- KURASHIFT: 物件調査シート（Notion DB_物件購入検討 相当）— 値 + ソース
-- Project: jarvis-dashboard

create table if not exists public.kurashift_re_deal_field_values (
  id uuid primary key default gen_random_uuid(),
  deal_id uuid not null references public.kurashift_re_deals(id) on delete cascade,
  field_id text not null,
  value_text text,
  value_number numeric,
  source_type text not null default 'manual'
    check (source_type in (
      'inbound_mail', 'outbound_mail', 'grok', 'web', 'deal', 'manual', 'formula', 'pdf'
    )),
  source_ref text,
  source_excerpt text,
  confidence text not null default 'medium'
    check (confidence in ('high', 'medium', 'low')),
  status text not null default 'suggested'
    check (status in ('suggested', 'verified', 'rejected')),
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists kurashift_re_deal_field_values_deal_field_uidx
  on public.kurashift_re_deal_field_values (deal_id, field_id);

create index if not exists kurashift_re_deal_field_values_deal_status_idx
  on public.kurashift_re_deal_field_values (deal_id, status);

alter table public.kurashift_re_deal_field_values enable row level security;

drop policy if exists kurashift_re_deal_field_values_auth_all
  on public.kurashift_re_deal_field_values;
create policy kurashift_re_deal_field_values_auth_all
  on public.kurashift_re_deal_field_values
  for all to authenticated
  using (true)
  with check (true);
