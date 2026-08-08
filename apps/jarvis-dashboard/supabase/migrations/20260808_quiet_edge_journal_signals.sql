-- Quiet Edge: journal sleep signals for analysis join
alter table public.vital_journal_daily
  add column if not exists sleep_signal text not null default '',
  add column if not exists sleep_tags text[] not null default '{}'::text[];
