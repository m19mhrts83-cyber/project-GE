-- 定額 AI の依頼箱（2026-11-13 従量課金ゼロ化）。
-- ダッシュボードは依頼を置いて待つだけ。Mac の係（scripts/jarvis_flat_ai_worker.py）が
-- GenCode／Codex／Cursor／Claude の定額枠で作って結果を書く。従量課金の AI API は呼ばない。
-- 中身はメール等の私的な文面を含むので、service_role だけが読める。古い行は係が 3 日で消す。
create table if not exists public.ai_jobs (
  id uuid primary key default gen_random_uuid(),
  prompt_hash text not null,
  purpose text not null default 'reply',
  interactive boolean not null default true,
  prompt text not null,
  images jsonb,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'done', 'error')),
  result text,
  provider text,
  notes jsonb,
  error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  -- 画面に返した時刻。返す前の結果だけを「もう一度押した」ときに使い回す（作り直しは新しい依頼）
  delivered_at timestamptz
);

create index if not exists ai_jobs_queued_idx on public.ai_jobs (created_at) where status = 'queued';
create index if not exists ai_jobs_hash_idx on public.ai_jobs (prompt_hash, created_at desc);

alter table public.ai_jobs enable row level security;
revoke all on public.ai_jobs from anon, authenticated;
grant select, insert, update, delete on public.ai_jobs to service_role;

comment on table public.ai_jobs is
  'Flat-rate AI job queue: Dashboard enqueues, Mac worker answers with subscription CLIs. No metered AI API.';

-- Mac 見張り（停止時だけ Slack #ops に 🔴、復旧で 🟢）。
create table if not exists public.mac_watch_status (
  check_id text primary key,
  notified_state text not null default 'unknown'
    check (notified_state in ('unknown', 'online', 'offline')),
  state_changed_at timestamptz,
  updated_at timestamptz not null default now()
);

alter table public.mac_watch_status enable row level security;
revoke all on public.mac_watch_status from anon, authenticated;
grant select, insert, update on public.mac_watch_status to service_role;

insert into public.mac_watch_status (check_id) values ('mac'), ('flat_ai_worker')
on conflict (check_id) do nothing;
