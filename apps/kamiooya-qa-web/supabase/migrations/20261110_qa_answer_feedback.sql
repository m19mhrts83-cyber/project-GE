-- (2) 回答の評価（2026-11-10）。追加のみ。段階公開スイッチ answer_feedback の対象者だけが書く。
-- 1人が1つの回答に付けられる評価は1件（付け直しは上書き）。読み書きは service_role だけ。
create table if not exists public.qa_answer_feedback (
  id bigint generated always as identity primary key,
  user_id text not null,
  chat_id text not null,
  message_id text not null,
  rating text not null check (rating in ('good','bad','great')),
  comment text not null default '' check (char_length(comment) <= 1000),
  question text not null default '',
  answer text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, chat_id, message_id)
);
alter table public.qa_answer_feedback enable row level security;
revoke all on public.qa_answer_feedback from public, anon, authenticated;
grant select, insert, update on public.qa_answer_feedback to service_role;
create index if not exists qa_answer_feedback_created on public.qa_answer_feedback(created_at desc);
