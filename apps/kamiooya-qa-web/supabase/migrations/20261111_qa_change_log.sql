-- 改善履歴（2026-11-11 松野さん）。会員の声を受けて直したことを、アプリの「改善履歴」タブで共有する。追加のみ。
-- 段階公開スイッチ change_log が見える人だけが読める。書くのは Miss Lemon（service_role）だけ。
-- 会員の名前や評価の本文は書かない。きっかけは件数と理由の種類だけにする。
create table if not exists public.qa_change_log (
  id bigint generated always as identity primary key,
  released_on date not null,
  title text not null check (char_length(title) between 1 and 120),
  body text not null default '' check (char_length(body) <= 600),
  trigger text not null default '' check (char_length(trigger) <= 200),
  visible boolean not null default true,
  created_at timestamptz not null default now()
);
alter table public.qa_change_log enable row level security;
revoke all on public.qa_change_log from public, anon, authenticated;
grant select, insert, update, delete on public.qa_change_log to service_role;
create index if not exists qa_change_log_released on public.qa_change_log(released_on desc, id desc);

-- スイッチ: まず松野さんだけ（answer_feedback と同じ名指し）。
insert into public.qa_feature_flags(feature, stage, owner_ids, reviewer_ids, note)
select 'change_log', 'owner', owner_ids, reviewer_ids, '改善履歴タブ（声を受けて直したことの共有）'
from public.qa_feature_flags where feature = 'answer_feedback'
on conflict (feature) do nothing;
notify pgrst, 'reload schema';
