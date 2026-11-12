-- キーワード検索（全データ）の利用記録（2026-11-12 松野さん「キーワード検索の検索数も評価に入れて、チャットの質問と別に見たい」）。追加のみ。
-- チャットの質問（app_qa_search_events）とは別の表にする。費用の実測・質問ランキング（qa_theme_source_digest）に混ざらないため。
-- 1回の検索＝1行。query_text は画面と同じ正規化（全角→半角・小文字・空白1つ・OR は「 または 」）をした後の文字列。
-- hits はデータソースごとの当たり件数 {comments, openchat, lessons, knowledge}。オプチャはサーバーの上限（最大200件）までの数。
create table if not exists public.qa_keyword_search_events (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  user_id text,
  session_id text,
  query_text text not null check (char_length(query_text) between 1 and 500),
  term_count integer,
  has_or boolean not null default false,
  hit_total integer,
  hits jsonb not null default '{}'::jsonb,
  result_status text not null default 'ok' check (result_status in ('ok', 'partial', 'error'))
);

create index if not exists qa_keyword_search_events_created_at_idx
  on public.qa_keyword_search_events (created_at desc);

alter table public.qa_keyword_search_events enable row level security;
revoke all on table public.qa_keyword_search_events from public, anon, authenticated;
grant select, insert on table public.qa_keyword_search_events to service_role;
grant usage, select on sequence public.qa_keyword_search_events_id_seq to service_role;
