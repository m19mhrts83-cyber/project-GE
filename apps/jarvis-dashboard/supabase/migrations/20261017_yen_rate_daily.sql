-- 615 円動向報告係 — USD/JPY 日次レート投影（jarvis-dashboard）
-- Data API 明示 GRANT（2026-10-30〜）必須

create table if not exists public.yen_rate_daily (
  trade_date date not null,
  symbol text not null default 'USDJPY',
  close numeric not null,
  high numeric,
  low numeric,
  source text,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (trade_date, symbol)
);

create index if not exists yen_rate_daily_symbol_date_idx
  on public.yen_rate_daily (symbol, trade_date desc);

alter table public.yen_rate_daily enable row level security;

drop policy if exists yen_rate_daily_select_authenticated on public.yen_rate_daily;
create policy yen_rate_daily_select_authenticated
  on public.yen_rate_daily
  for select
  to authenticated
  using (true);

drop policy if exists yen_rate_daily_all_service_role on public.yen_rate_daily;
create policy yen_rate_daily_all_service_role
  on public.yen_rate_daily
  for all
  to service_role
  using (true)
  with check (true);

grant select on table public.yen_rate_daily to authenticated;
grant select, insert, update, delete on table public.yen_rate_daily to service_role;
