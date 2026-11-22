-- 運営分析: 管理者が画面から質問ランキング（講座テーマ案・オプチャ）を作り直した記録（2026-11-23 松野さん）。
-- 「好きなタイミングで集計したい」。押すと raimo-auth が GitHub Actions course-theme weekly を起動する（Gemini 従量）。
-- 読み書きは service_role（raimo-auth）だけ。押した人の ID と日時、起動できたかを残す。
create table if not exists public.qa_ranking_rebuilds (
  id bigserial primary key,
  requested_by text not null default '',
  requested_at timestamptz not null default now(),
  dispatched boolean not null default false,
  error text not null default '' check (char_length(error) <= 200)
);
create index if not exists qa_ranking_rebuilds_requested_at on public.qa_ranking_rebuilds (requested_at desc);
alter table public.qa_ranking_rebuilds enable row level security;
revoke all on public.qa_ranking_rebuilds from public, anon, authenticated;
grant select, insert, update on public.qa_ranking_rebuilds to service_role;
grant usage, select on sequence public.qa_ranking_rebuilds_id_seq to service_role;
