-- inquiry_status に awaiting_grok を追加（Grok handoff 待受）
alter table public.kurashift_re_deals
  drop constraint if exists kurashift_re_deals_inquiry_status_check;

alter table public.kurashift_re_deals
  add constraint kurashift_re_deals_inquiry_status_check
  check (inquiry_status in (
    'none', 'draft', 'sending', 'sent', 'awaiting_reply', 'awaiting_grok', 'has_reply'
  ));
