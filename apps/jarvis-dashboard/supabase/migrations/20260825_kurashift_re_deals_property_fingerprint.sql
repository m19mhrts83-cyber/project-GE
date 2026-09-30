-- KURASHIFT: 千三つ案件の物件 fingerprint（DB 側重複マージ・送信ガード）
-- Project: jarvis-dashboard

alter table public.kurashift_re_deals
  add column if not exists property_fingerprint text;

create index if not exists kurashift_re_deals_property_fingerprint_idx
  on public.kurashift_re_deals (property_fingerprint)
  where property_fingerprint is not null;
