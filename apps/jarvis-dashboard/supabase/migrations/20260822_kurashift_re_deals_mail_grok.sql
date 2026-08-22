-- Grok [Grok調査] 取込 source=mail_grok を許可
alter table public.kurashift_re_deals
  drop constraint if exists kurashift_re_deals_source_check;

alter table public.kurashift_re_deals
  add constraint kurashift_re_deals_source_check
  check (source in (
    'mail_admin', 'mail_estate', 'mail_grok',
    'kenbiya', 'rakumachi', 'manual', 'other'
  ));
