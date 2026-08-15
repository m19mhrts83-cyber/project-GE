-- MQ会計評価 Phase E: 軽量B/Sスナップショット
-- jarvis-dashboard のみ。kamiooya-qa には作らない。
-- NULL = 未入力（要確認）。ゼロ埋めして「完成」扱いにしない。

create table if not exists public.kurashift_mq_bs_snapshots (
  id uuid primary key default gen_random_uuid(),
  business_line text not null
    check (business_line in ('realestate', 'ai')),
  entity text not null
    check (entity in ('personal', 'corporate')),
  -- 基準日（月初でも月末でも可。表示は as_of を正）
  as_of_date date not null,
  -- 資産（NULL=要確認）
  cash numeric,
  receivables numeric,
  -- 賃貸は棚卸なし想定。入力してもよいが UI で注記する
  inventory numeric,
  fixed_assets numeric,
  -- 負債・資本（NULL=要確認）
  liabilities_st numeric,
  liabilities_lt numeric,
  capital numeric,
  retained_earnings numeric,
  -- 当期利益。NULLなら同期間の MQ の G を参考表示（DBには捏造保存しない）
  current_profit numeric,
  note text,
  source text not null default 'manual'
    check (source in ('manual', 'jarvis', 'import')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_line, entity, as_of_date)
);

create index if not exists kurashift_mq_bs_snapshots_asof_idx
  on public.kurashift_mq_bs_snapshots (as_of_date desc);

create index if not exists kurashift_mq_bs_snapshots_line_entity_idx
  on public.kurashift_mq_bs_snapshots (business_line, entity, as_of_date desc);

alter table public.kurashift_mq_bs_snapshots enable row level security;

drop policy if exists kurashift_mq_bs_snapshots_auth_all
  on public.kurashift_mq_bs_snapshots;
create policy kurashift_mq_bs_snapshots_auth_all
  on public.kurashift_mq_bs_snapshots
  for all to authenticated
  using (true)
  with check (true);

comment on table public.kurashift_mq_bs_snapshots is
  'MQ軽量B/S。欠損はNULLのまま。合算はアプリ合成。棚卸は賃貸で通常未使用。';
