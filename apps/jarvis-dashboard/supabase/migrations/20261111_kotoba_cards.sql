-- ことばの棚（kotoba）段1: 記録の土台
-- 設計: Claude Doc「ことばの棚 設計案」(2026-11-09, 松野さん了承)
--
-- 録音・議事録・Journal から拾った「あとで効く言葉」を1件1枚のカードで持つ。
-- タスクにはしない（タスクは 312 → Todoist）。拾い元の母体はコミュニケーション台帳（comm_items）にそろえ、
-- 台帳から来たカードは comm_item_id でつなぐ（台帳②セカンドブレインの取り込みができたら、そこから候補を受け取る）。
--
--   kotoba_cards : カード本体（原文・誰が・どこで・種類・棚・判断の状態）
--   kotoba_notes : 自分のひとこと（カードごと）と棚ごとのまとめ
--
-- 判断（残す／いらない／迷う）は owner_decisions（surface=kotoba）にも残す。ここの status は今の状態だけ。
-- 自分用の記録で他人の発言も入るため service_role のみ GRANT（anon / authenticated なし）。

create table if not exists public.kotoba_cards (
  id uuid primary key default gen_random_uuid(),
  body text not null check (char_length(body) between 1 and 1000),
  speaker text,                                  -- 実名。不明なら null（推測しない）
  speaker_guess boolean not null default false,  -- 「推定」のとき true
  where_label text,                              -- 例: 融資戦略の面談／ループウェアDay2
  occurred_on date,
  at_label text,                                 -- 録音内のおおよその位置（例: 約12分）
  source text not null default 'manual'
    check (source in ('genspark', 'notion', 'journal', 'slack', 'comm_hub', 'manual')),
  source_ref jsonb not null default '{}'::jsonb, -- task_id / notion_page / url など
  comm_item_id uuid references public.comm_items(id) on delete set null,
  background text,                               -- AI が書く背景1行
  kind text not null default 'insight'
    check (kind in ('insight', 'cheer', 'criterion', 'question', 'self_note')),
  shelves text[] not null default '{}',
  is_summary boolean not null default false,     -- 原文ではなく要約文から拾ったもの
  status text not null default 'candidate'
    check (status in ('candidate', 'kept', 'dropped', 'hesitated')),
  dedupe_key text not null unique,               -- 同じ発言の二重登録を防ぐ（例: genspark:<task_id>:<連番>）
  decided_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists kotoba_cards_status_idx on public.kotoba_cards (status, created_at desc);
create index if not exists kotoba_cards_shelves_idx on public.kotoba_cards using gin (shelves);
create index if not exists kotoba_cards_comm_item_idx on public.kotoba_cards (comm_item_id) where comm_item_id is not null;

create table if not exists public.kotoba_notes (
  id bigint generated always as identity primary key,
  card_id uuid references public.kotoba_cards(id) on delete cascade,
  shelf text,                                    -- 棚ごとのまとめ・感想のとき
  kind text not null default 'comment' check (kind in ('comment', 'summary')),
  body text not null check (char_length(body) between 1 and 4000),
  created_at timestamptz not null default now(),
  check (card_id is not null or shelf is not null)
);

create index if not exists kotoba_notes_card_idx on public.kotoba_notes (card_id, created_at desc);
create index if not exists kotoba_notes_shelf_idx on public.kotoba_notes (shelf, created_at desc);

alter table public.kotoba_cards enable row level security;
alter table public.kotoba_notes enable row level security;
revoke all on public.kotoba_cards from anon, authenticated;
revoke all on public.kotoba_notes from anon, authenticated;
grant select, insert, update, delete on public.kotoba_cards to service_role;
grant select, insert, update, delete on public.kotoba_notes to service_role;
grant usage, select on sequence public.kotoba_notes_id_seq to service_role;

comment on table public.kotoba_cards is 'ことばの棚: タスク以外の「あとで効く言葉」1件1枚。判断ログは owner_decisions(surface=kotoba)';
comment on table public.kotoba_notes is 'ことばの棚: カードへのひとこと・棚ごとのまとめ';
