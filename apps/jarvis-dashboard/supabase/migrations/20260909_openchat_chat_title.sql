-- オプチャタイトル付き集約（Grok / 参照用）
alter table public.kurashift_openchat_logs
  add column if not exists chat_title text;

alter table public.kurashift_openchat_logs
  add column if not exists source_system text not null default 'line_openchat';

alter table public.kurashift_openchat_logs
  add column if not exists ingest_status text not null default 'active';

create index if not exists kurashift_openchat_logs_chat_title_idx
  on public.kurashift_openchat_logs (chat_title);
