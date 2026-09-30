-- S9 mgmt: property_lane / vacancy_listing_ok / precheck_sent_at
-- jarvis-dashboard

alter table public.kurashift_re_mgmt_vendors
  add column if not exists property_lane text,
  add column if not exists vacancy_listing_ok boolean,
  add column if not exists precheck_sent_at date;

create index if not exists kurashift_re_mgmt_vendors_lane_idx
  on public.kurashift_re_mgmt_vendors (property_lane, status);

create index if not exists kurashift_re_mgmt_vendors_vacancy_ok_idx
  on public.kurashift_re_mgmt_vendors (vacancy_listing_ok)
  where vacancy_listing_ok is true;
