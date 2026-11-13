-- AIエージェント運用成熟度: 週1回の計測記録
-- 設計: Claude Doc「AIエージェント運用成熟度 評価 設計案」(2026-11-13, 松野さん了承)
--
-- scripts/jarvis_agent_maturity.py が土曜に 1 行ずつ足す（過去の行は書き換えない）。
-- scope = 'team'（チーム全体）または社員番号（'116' など。1フォルダ1社員）。
-- metrics: 指標ごとの実測値 {"key": {"value": 0.97, "num": 33, "den": 34, "note": "..."}}。取れない指標は入れない（推測で埋めない）。
-- 項目のレベル（L1〜L5）は画面側で config/agent_maturity.json の固定ラインから計算する。
-- 自分用の記録なので service_role のみ。

create table if not exists public.agent_maturity_snapshots (
  id bigserial primary key,
  measured_on date not null,
  scope text not null default 'team' check (scope ~ '^(team|[0-9]{3})$'),
  metrics jsonb not null default '{}'::jsonb,
  method text not null default 'auto',
  created_at timestamptz not null default now(),
  unique (measured_on, scope)
);

create index if not exists agent_maturity_snapshots_scope_idx
  on public.agent_maturity_snapshots (scope, measured_on desc);

alter table public.agent_maturity_snapshots enable row level security;
revoke all on public.agent_maturity_snapshots from anon, authenticated;
grant select, insert on public.agent_maturity_snapshots to service_role;
grant usage, select on sequence public.agent_maturity_snapshots_id_seq to service_role;
