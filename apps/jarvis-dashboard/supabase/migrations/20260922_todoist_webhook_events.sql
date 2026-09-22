-- Todoist Webhook 受信ログ（jarvis-dashboard / jarvis-dashboard PJ）
-- delivery_id は UNIQUE（Postgres は NULL を複数許可 → ヘッダ無しも insert 可）
create table if not exists public.todoist_webhook_events (
  id bigserial primary key,
  delivery_id text unique,
  event_name text not null,
  user_id text,
  event_data jsonb not null default '{}'::jsonb,
  event_data_extra jsonb,
  initiator jsonb,
  processed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists todoist_webhook_events_created_idx
  on public.todoist_webhook_events (created_at desc);

create index if not exists todoist_webhook_events_unprocessed_idx
  on public.todoist_webhook_events (processed_at, created_at)
  where processed_at is null;

alter table public.todoist_webhook_events enable row level security;

drop policy if exists todoist_webhook_events_auth_all on public.todoist_webhook_events;
create policy todoist_webhook_events_auth_all on public.todoist_webhook_events
  for all to authenticated using (true) with check (true);
