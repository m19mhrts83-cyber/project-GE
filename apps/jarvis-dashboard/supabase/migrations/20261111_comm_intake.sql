-- コミュニケーション台帳の受付の表（comm_intake）
-- jarvis-dashboard PJ（idkdqneutpvkhxhpjtgc）
-- ボット（Grok など）が POST /api/comm-intake で直接登録する。ここは「受付」だけで、
-- 台帳本体 comm_items への本登録は jarvis_comm_hub.py ingest-intake（取込ゲート→名簿→分類）が行う。
-- 個人情報が入りうるため service_role のみ（anon / authenticated なし）。

create table if not exists public.comm_intake (
  id uuid primary key default gen_random_uuid(),
  source_bot text not null,                  -- 鍵から決まる送り手（例: grok）
  bot_item_id text not null,                 -- ボット側の一意キー（重複は受け付け済み扱い）
  payload jsonb not null default '{}'::jsonb,
  received_at timestamptz not null default now(),
  status text not null default 'new'
    check (status in ('new', 'ingested', 'rejected')),
  error text,                                -- rejected の理由・取り込み失敗の理由
  ingested_item_id uuid references public.comm_items(id) on delete set null,
  updated_at timestamptz not null default now(),
  unique (source_bot, bot_item_id)
);

create index if not exists comm_intake_status_idx
  on public.comm_intake (status, received_at);
create index if not exists comm_intake_bot_time_idx
  on public.comm_intake (source_bot, received_at desc);

alter table public.comm_intake enable row level security;
revoke all on table public.comm_intake from anon, authenticated;
grant select, insert, update, delete on table public.comm_intake to service_role;
