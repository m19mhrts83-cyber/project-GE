-- 下書きレビュー（draft_reviews）— Nody の /drafts で、箇所を選んで声でダメ出し → AI が直す → 差分で確認
-- jarvis-dashboard PJ（idkdqneutpvkhxhpjtgc）
--
-- 1行 = 1つの下書き。versions に版（v1, v2 …）を積む。消さずに追記する。
--   versions[] = { label, text, at, by: 'agent'|'ai'|'owner', comments: [{quote,start,end,text,via}], note, reverted? }
-- 版が増えるたびに owner_decisions（surface=draft_review）へ判断ログを1行書く（アプリ側 lib/ownerDecisionLog.ts）。
-- 下書きを置くのはエージェント（scripts/jarvis_draft_decision_log.py push）か、画面に貼り付け。
-- 個人情報が入るため service_role のみ GRANT。

create table if not exists public.draft_reviews (
  id uuid primary key default gen_random_uuid(),
  case_name text not null,                 -- 例: 20261107_次のご提案
  recipient text not null,                 -- 例: 今村さん（ルールの partner: と同じ書き方）
  channel text not null default 'other'
    check (channel in ('chatwork','mail','line','slack','doc','other')),
  status text not null default 'open'
    check (status in ('open','done','dropped')),
  context text,                            -- 下書きの前提（採用済みルール・相手の事情など。AI に渡す）
  versions jsonb not null default '[]'::jsonb,
  source text not null default 'loopware', -- loopware / script
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists draft_reviews_status_time_idx
  on public.draft_reviews (status, updated_at desc);

alter table public.draft_reviews enable row level security;
revoke all on table public.draft_reviews from anon, authenticated;
grant select, insert, update, delete on table public.draft_reviews to service_role;
