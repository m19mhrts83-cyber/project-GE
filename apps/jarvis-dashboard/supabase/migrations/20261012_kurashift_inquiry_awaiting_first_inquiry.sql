-- inquiry_status: S1 kurashift_handoff 後の第一問合せ待ち（旧 awaiting_grok 誤用を分離）
alter table public.kurashift_re_deals
  drop constraint if exists kurashift_re_deals_inquiry_status_check;

alter table public.kurashift_re_deals
  add constraint kurashift_re_deals_inquiry_status_check
  check (
    inquiry_status is null
    or inquiry_status in (
      'none',
      'draft',
      'sending',
      'sent',
      'awaiting_reply',
      'awaiting_first_inquiry',
      'awaiting_grok',
      'has_reply'
    )
  );

comment on column public.kurashift_re_deals.inquiry_status is
  'none|draft|sending|sent|awaiting_reply|awaiting_first_inquiry|awaiting_grok|has_reply';
