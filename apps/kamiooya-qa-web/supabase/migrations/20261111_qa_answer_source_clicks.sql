-- (2) 判断ログの補足: 会員が答えの根拠を開いた記録（2026-11-10 松野さん）。追加のみ。
-- スイッチ answer_feedback が見える人の操作だけが入る。同じ回答で同じ根拠を何度開いても1行（最後に開いた時刻と操作で上書き）。
create table if not exists public.qa_answer_source_clicks (
  user_id text not null,
  chat_id text not null,
  message_id text not null,
  kind text not null check (kind in ('comment','openchat','lesson','video_chunk')),
  source_key text not null check (char_length(source_key) between 1 and 300),
  title text not null default '' check (char_length(title) <= 300),
  label text not null default '' check (char_length(label) <= 50),
  action text not null check (action in ('open_text','open_link','jump')),
  question text not null default '' check (char_length(question) <= 2000),
  clicked_at timestamptz not null default now(),
  primary key (user_id, chat_id, message_id, kind, source_key)
);
alter table public.qa_answer_source_clicks enable row level security;
revoke all on public.qa_answer_source_clicks from public, anon, authenticated;
grant select, insert, update, delete on public.qa_answer_source_clicks to service_role;
create index if not exists qa_answer_source_clicks_at on public.qa_answer_source_clicks(clicked_at desc);
