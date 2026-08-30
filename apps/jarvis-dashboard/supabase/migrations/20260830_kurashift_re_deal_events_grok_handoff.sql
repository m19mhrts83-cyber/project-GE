-- Grok依頼の判断履歴 event_type を許可
ALTER TABLE public.kurashift_re_deal_events
  DROP CONSTRAINT IF EXISTS kurashift_re_deal_events_event_type_check;

ALTER TABLE public.kurashift_re_deal_events
  ADD CONSTRAINT kurashift_re_deal_events_event_type_check
  CHECK (event_type = ANY (ARRAY[
    'created'::text,
    'status_change'::text,
    'inquiry_sent'::text,
    'inquiry_reply'::text,
    'grok_applied'::text,
    'grok_handoff_sent'::text,
    'grok_handoff_ready'::text,
    'review_confirm'::text,
    'review_pass'::text,
    'note'::text
  ]));
