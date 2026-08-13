-- card_settlement_buffer kind for Olive/card debit funding playbook
ALTER TABLE public.kurashift_money_ops DROP CONSTRAINT IF EXISTS kurashift_money_ops_kind_check;
ALTER TABLE public.kurashift_money_ops ADD CONSTRAINT kurashift_money_ops_kind_check CHECK (
  kind = ANY (
    ARRAY[
      'bank_transfer'::text,
      'broker_transfer'::text,
      'securities_cash'::text,
      'insurance_alloc'::text,
      'card_settlement_buffer'::text
    ]
  )
);
