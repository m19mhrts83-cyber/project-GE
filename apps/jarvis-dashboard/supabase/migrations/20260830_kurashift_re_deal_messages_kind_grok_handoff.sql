-- Grok依頼送信の message.kind = grok_handoff を許可
-- （送信後の insert が kind_check で落ち、inquiry_status が sending のまま残る不具合）
ALTER TABLE public.kurashift_re_deal_messages
  DROP CONSTRAINT IF EXISTS kurashift_re_deal_messages_kind_check;

ALTER TABLE public.kurashift_re_deal_messages
  ADD CONSTRAINT kurashift_re_deal_messages_kind_check
  CHECK (kind IN ('first_inquiry', 'reply', 'note', 'grok_handoff'));
