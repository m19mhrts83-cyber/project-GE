-- LINE 公式アカウント（Messaging API）Webhook 受信ログ
-- jarvis-dashboard / jarvis-dashboard PJ
-- 目的: Tcell 等のグループ LINE 本文を OA Bot 経由で平文取得する PoC の受け皿。
--       受信のみ（push 0通）。Mac 側の pull が processed_at を立てて 5.やり取り.md へ流す。
-- webhook_event_id は UNIQUE（LINE の再送に対する冪等キー。NULL は複数許可）。

create table if not exists public.line_oa_events (
  id bigserial primary key,
  webhook_event_id text unique,
  destination text,
  event_type text not null,
  source_type text,
  group_id text,
  room_id text,
  user_id text,
  message_type text,
  message_id text,
  text text,
  reply_token text,
  event_timestamp bigint,
  raw jsonb not null default '{}'::jsonb,
  processed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists line_oa_events_created_idx
  on public.line_oa_events (created_at desc);

create index if not exists line_oa_events_unprocessed_idx
  on public.line_oa_events (processed_at, created_at)
  where processed_at is null;

create index if not exists line_oa_events_group_idx
  on public.line_oa_events (group_id, event_timestamp);

alter table public.line_oa_events enable row level security;

drop policy if exists line_oa_events_auth_all on public.line_oa_events;
create policy line_oa_events_auth_all on public.line_oa_events
  for all to authenticated using (true) with check (true);

-- 2026-10-30 以降: public 新規テーブルは Data API 用の明示 GRANT が必須
grant select, insert, update, delete on table public.line_oa_events to authenticated, service_role;
grant usage, select on sequence public.line_oa_events_id_seq to authenticated, service_role;
