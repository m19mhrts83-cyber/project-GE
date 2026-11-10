-- (2) 回答の評価に「どのAIで作った答えか」を残す（2026-11-11 松野さん）。追加のみ。
-- 悪いねの原因が軽いモデル（ライト版）なのか、使い回した答えなのかを、あとで見分けるため。
-- qa_answer_meta: 答えを作った（使い回した）ときに raimo-auth が1行書く。本文は持たず、本文のハッシュで評価と結び付ける。
create table if not exists public.qa_answer_meta (
  user_id text not null,
  chat_id text not null,
  answer_hash text not null check (answer_hash ~ '^[0-9a-f]{64}$'),
  mode text not null check (mode in ('normal','fast','semantic','deep')),
  tier text not null default 'standard' check (tier in ('lite','standard')),
  model text not null default '' check (char_length(model) <= 80),
  reused boolean not null default false,
  created_at timestamptz not null default now(),
  primary key (user_id, chat_id, answer_hash)
);
alter table public.qa_answer_meta enable row level security;
revoke all on public.qa_answer_meta from public, anon, authenticated;
grant select, insert, update on public.qa_answer_meta to service_role;
create index if not exists qa_answer_meta_created on public.qa_answer_meta(created_at desc);

-- 評価の行にも写す（評価した時点の答えの作り方）。この移行より前の評価は空のまま＝不明。
alter table public.qa_answer_feedback add column if not exists answer_mode text;
alter table public.qa_answer_feedback add column if not exists answer_tier text;
alter table public.qa_answer_feedback add column if not exists answer_model text;
alter table public.qa_answer_feedback add column if not exists answer_reused boolean;
notify pgrst, 'reload schema';
