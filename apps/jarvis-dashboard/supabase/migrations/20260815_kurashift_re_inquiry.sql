-- KURASHIFT: 千三つ 第一問い合わせ＋返信蓄積（箱）
-- Project: jarvis-dashboard

-- consultations lane に realestate を追加
alter table public.kurashift_consultations
  drop constraint if exists kurashift_consultations_lane_check;

alter table public.kurashift_consultations
  add constraint kurashift_consultations_lane_check
  check (lane in ('general', 'lifeplan', 'theme', 'tax', 'core', 'realestate'));

-- deals: 問い合わせ状態
alter table public.kurashift_re_deals
  add column if not exists inquiry_status text not null default 'none';

alter table public.kurashift_re_deals
  drop constraint if exists kurashift_re_deals_inquiry_status_check;

alter table public.kurashift_re_deals
  add constraint kurashift_re_deals_inquiry_status_check
  check (inquiry_status in ('none', 'draft', 'sent', 'awaiting_reply', 'has_reply'));

alter table public.kurashift_re_deals
  add column if not exists inquiry_thread_id text;

alter table public.kurashift_re_deals
  add column if not exists inquiry_sent_at timestamptz;

create index if not exists kurashift_re_deals_inquiry_status_idx
  on public.kurashift_re_deals (inquiry_status, inquiry_sent_at desc nulls last);

-- 送受信メッセージ（第一送信・返信・メモ）
create table if not exists public.kurashift_re_deal_messages (
  id uuid primary key default gen_random_uuid(),
  deal_id uuid not null references public.kurashift_re_deals(id) on delete cascade,
  direction text not null
    check (direction in ('outbound', 'inbound')),
  kind text not null default 'note'
    check (kind in ('first_inquiry', 'reply', 'note')),
  gmail_id text,
  thread_id text,
  from_email text,
  to_email text,
  subject text,
  body_text text not null default '',
  occurred_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists kurashift_re_deal_messages_gmail_id_uidx
  on public.kurashift_re_deal_messages (gmail_id)
  where gmail_id is not null;

create index if not exists kurashift_re_deal_messages_deal_at_idx
  on public.kurashift_re_deal_messages (deal_id, occurred_at desc);
