-- コミュニケーション台帳（comm hub）Phase 0
-- jarvis-dashboard PJ（idkdqneutpvkhxhpjtgc）
-- 設計: Claude Doc「コミュニケーション集約DB 設計案」(2026-11-03, 松野さん承認)
--
-- 3 テーブル:
--   comm_parties : 相手の名簿（連絡先一覧.yaml から同期。must_check = 必ず確認）
--   comm_items   : 台帳本体（1通 = 1行）。取込ゲートを通ったものだけ
--   comm_links   : 何の件か（deal / owned_property / triage_item / todoist_task / vendor）
--
-- 正本の分担: 全文 = OneDrive 5.やり取り.md、分類と対応状況 = この台帳、タスク = Todoist。
-- 個人情報が集まるため service_role のみ GRANT（anon / authenticated なし）。

create extension if not exists vector with schema extensions;
create extension if not exists pgroonga with schema extensions;

-- ---------------------------------------------------------------- parties
create table if not exists public.comm_parties (
  party_id text primary key,                 -- 例: partner:102_ミニテック
  kind text not null default 'other'
    check (kind in ('mgmt','repair','insurance','finance','tenant','learning',
                    'club','agency','broker','vendor','bank','self','other')),
  name text not null,
  partner_folder text,                       -- 26_パートナー社への相談 配下のフォルダ名
  emails text[] not null default '{}',
  email_domains text[] not null default '{}',
  chat_ids jsonb not null default '{}'::jsonb,  -- chatwork_room_id / line mid 等
  must_check boolean not null default false,
  source text not null default 'contact_yaml',
  active boolean not null default true,
  payload jsonb not null default '{}'::jsonb,
  synced_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists comm_parties_folder_idx on public.comm_parties (partner_folder);

-- ---------------------------------------------------------------- items
create table if not exists public.comm_items (
  id uuid primary key default gen_random_uuid(),
  channel text not null
    check (channel in ('gmail','chatwork','line','line_oa','imessage','slack',
                       'obsidian','other')),
  account text not null default '',
  external_id text not null,                 -- 取込元での一意キー（md 由来は md:<sha1>）
  thread_key text,
  occurred_at timestamptz not null,
  direction text not null check (direction in ('inbound','outbound')),
  party_id text references public.comm_parties(party_id) on delete set null,
  category text not null
    check (category in ('partner','property','inquiry','self','agent')),
  tags text[] not null default '{}',
  ingest_status text not null default 'staging'
    check (ingest_status in ('staging','ready','excluded')),
  work_status text not null default 'new'
    check (work_status in ('new','needs_reply','drafted','waiting','done','no_action')),
  priority text check (priority in ('high','med','low')),
  due_on date,
  subject text,
  summary text,
  body_text text,
  context_header text,                       -- 「相手｜フォルダ｜チャネル｜向き｜日時」検索用の頭書き
  search_text text generated always as (
    coalesce(context_header, '') || ' ' || coalesce(subject, '') || ' ' ||
    coalesce(summary, '') || ' ' || coalesce(body_text, '')
  ) stored,
  embedding extensions.vector(768),          -- 後から埋める（kamiooya-qa と同じ 768 次元）
  source_ref jsonb not null default '{}'::jsonb,  -- 正本への戻り道（md パス・見出し・gmail id 等）
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (channel, account, external_id)
);

create index if not exists comm_items_party_time_idx
  on public.comm_items (party_id, occurred_at desc);
create index if not exists comm_items_category_time_idx
  on public.comm_items (category, occurred_at desc);
create index if not exists comm_items_work_idx
  on public.comm_items (work_status, occurred_at desc)
  where work_status in ('new','needs_reply','drafted','waiting');
create index if not exists comm_items_ready_time_idx
  on public.comm_items (ingest_status, occurred_at desc);
create index if not exists comm_items_tags_idx
  on public.comm_items using gin (tags);
create index if not exists comm_items_search_pgroonga_idx
  on public.comm_items using pgroonga (search_text);

-- ---------------------------------------------------------------- links
create table if not exists public.comm_links (
  id bigserial primary key,
  item_id uuid not null references public.comm_items(id) on delete cascade,
  target_type text not null
    check (target_type in ('deal','owned_property','triage_item','todoist_task','vendor')),
  target_id text not null,
  role text,
  created_at timestamptz not null default now(),
  unique (item_id, target_type, target_id)
);

create index if not exists comm_links_target_idx
  on public.comm_links (target_type, target_id);

-- ---------------------------------------------------------------- 既存キューとの接続
alter table public.triage_items
  add column if not exists comm_item_id uuid;

-- ---------------------------------------------------------------- updated_at
create or replace function public.comm_items_touch()
returns trigger language plpgsql
set search_path = public
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists comm_items_touch on public.comm_items;
create trigger comm_items_touch before update on public.comm_items
  for each row execute function public.comm_items_touch();

-- ---------------------------------------------------------------- 検索
-- 分類で先に絞り、query があるときだけ PGroonga（日本語可）で絞る。
-- 意味検索（embedding）と RRF 合成は embedding を埋める段階で追加する。
create or replace function public.comm_search(
  p_party_ids text[] default null,
  p_categories text[] default null,
  p_channels text[] default null,
  p_since timestamptz default null,
  p_until timestamptz default null,
  p_query text default null,
  p_limit int default 50
)
returns table (
  id uuid,
  occurred_at timestamptz,
  channel text,
  direction text,
  party_id text,
  category text,
  work_status text,
  subject text,
  summary text,
  body_text text,
  source_ref jsonb,
  score float
)
language sql
stable
set search_path = public, extensions
as $$
  select
    i.id, i.occurred_at, i.channel, i.direction, i.party_id, i.category,
    i.work_status, i.subject, i.summary, i.body_text, i.source_ref,
    case when coalesce(trim(p_query), '') = '' then 0::float
         else extensions.pgroonga_score(i.tableoid, i.ctid)::float end as score
  from public.comm_items i
  where i.ingest_status = 'ready'
    and (p_party_ids is null or i.party_id = any(p_party_ids))
    and (p_categories is null or i.category = any(p_categories))
    and (p_channels is null or i.channel = any(p_channels))
    and (p_since is null or i.occurred_at >= p_since)
    and (p_until is null or i.occurred_at < p_until)
    and (coalesce(trim(p_query), '') = '' or i.search_text &@~ p_query)
  order by score desc, i.occurred_at desc
  limit greatest(1, least(coalesce(p_limit, 50), 500));
$$;

-- ---------------------------------------------------------------- RLS / GRANT
alter table public.comm_parties enable row level security;
alter table public.comm_items enable row level security;
alter table public.comm_links enable row level security;

revoke all on table public.comm_parties from anon, authenticated;
revoke all on table public.comm_items from anon, authenticated;
revoke all on table public.comm_links from anon, authenticated;

grant select, insert, update, delete on table public.comm_parties to service_role;
grant select, insert, update, delete on table public.comm_items to service_role;
grant select, insert, update, delete on table public.comm_links to service_role;
grant usage, select on sequence public.comm_links_id_seq to service_role;

revoke all on function public.comm_search(text[], text[], text[], timestamptz, timestamptz, text, int)
  from public, anon, authenticated;
grant execute on function public.comm_search(text[], text[], text[], timestamptz, timestamptz, text, int)
  to service_role;
