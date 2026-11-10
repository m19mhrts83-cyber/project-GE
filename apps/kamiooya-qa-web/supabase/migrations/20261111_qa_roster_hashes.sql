-- (3) 名簿照合用（2026-11-10）。追加のみ。平文の名前・会員番号は置かず、ハッシュだけを置く。
-- 同期: scripts/kamiooya_roster_sync.py が「目標設定・合格状況」シートを読み、全件入れ替える。
create table if not exists public.qa_roster_hashes (
  kind text not null check (kind in ('no','no_name')),
  hash text not null check (hash ~ '^[0-9a-f]{64}$'),
  primary key (kind, hash)
);
create table if not exists public.qa_roster_meta (
  id integer primary key default 1 check (id = 1),
  row_count integer not null default 0,
  synced_at timestamptz not null default now()
);
alter table public.qa_roster_hashes enable row level security;
alter table public.qa_roster_meta enable row level security;
revoke all on public.qa_roster_hashes, public.qa_roster_meta from public, anon, authenticated;
grant select, insert, update, delete on public.qa_roster_hashes, public.qa_roster_meta to service_role;
insert into public.qa_feature_flags (feature) values ('auto_approval') on conflict (feature) do nothing;
