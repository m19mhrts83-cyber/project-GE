-- (1) 同じ質問への答えの使い回し（2026-11-10）。追加のみ。段階公開スイッチ cost_saving の対象者の質問だけが使う。
-- 鍵は正規化した質問文の SHA-256。中身は講義・投稿から作った一般的な答えで、個人の情報は入れない。
create table if not exists public.qa_answer_cache (
  query_hash text primary key check (query_hash ~ '^[0-9a-f]{64}$'),
  query text not null default '' check (char_length(query) <= 4000),
  result jsonb not null,
  tier text not null default 'standard' check (tier in ('lite','standard')),
  hits integer not null default 0,
  created_at timestamptz not null default now(),
  last_hit_at timestamptz
);
alter table public.qa_answer_cache enable row level security;
revoke all on public.qa_answer_cache from public, anon, authenticated;
grant select, insert, update, delete on public.qa_answer_cache to service_role;
create index if not exists qa_answer_cache_created on public.qa_answer_cache(created_at);
