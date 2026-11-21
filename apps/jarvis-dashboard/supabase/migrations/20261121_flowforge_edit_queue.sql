-- FlowForge 修正文の待ち箱（2026-11-21）。
-- ChatGPT が MCP（/api/flowforge/mcp の queue_flowforge_edit）で、本人が了承した修正文を置く。
-- Mac のプログラム（scripts/jarvis_flowforge_assistant_paste.py --queue-once）が拾い、
-- 本人の Chrome で FlowForge の AIアシスタントへ入力・送信して、結果を書き戻す。
-- AI は呼ばない（FlowForge 画面の AIアシスタントだけが動く）。service_role だけが読める。
create table if not exists public.flowforge_edit_queue (
  id uuid primary key default gen_random_uuid(),
  agent_id text not null,
  flow_id text not null,
  instructions text not null,
  note text,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'sent', 'error', 'cancelled')),
  result text,
  error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);

create index if not exists flowforge_edit_queue_queued_idx
  on public.flowforge_edit_queue (created_at) where status = 'queued';

alter table public.flowforge_edit_queue enable row level security;
revoke all on public.flowforge_edit_queue from anon, authenticated;
grant select, insert, update, delete on public.flowforge_edit_queue to service_role;

comment on table public.flowforge_edit_queue is
  'FlowForge edit instructions approved by owner in ChatGPT; Mac program types them into FlowForge AI assistant.';
