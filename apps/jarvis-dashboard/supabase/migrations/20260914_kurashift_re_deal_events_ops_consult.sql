-- 運営相談フォーム送信・神大家紹介フォームの event_type を許可
ALTER TABLE public.kurashift_re_deal_events
  DROP CONSTRAINT IF EXISTS kurashift_re_deal_events_event_type_check;

ALTER TABLE public.kurashift_re_deal_events
  ADD CONSTRAINT kurashift_re_deal_events_event_type_check
  CHECK (event_type = ANY (ARRAY[
    'created'::text,
    'status_change'::text,
    'inquiry_sent'::text,
    'inquiry_reply'::text,
    'inquiry_kamiooya_form'::text,
    'ops_consult_form_submitted'::text,
    'grok_applied'::text,
    'grok_handoff_sent'::text,
    'grok_handoff_ready'::text,
    'review_confirm'::text,
    'review_pass'::text,
    'note'::text
  ]));
