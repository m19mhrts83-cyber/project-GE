-- 312 ループウェア判断ログ（task_loop_*）
-- jarvis-dashboard PJ。発言本文は comm_items を参照（二重保持しない）。
-- 313 は owner_decisions を正本（本 migration では触らない）。

create table if not exists public.task_loop_topics (
  id uuid primary key default gen_random_uuid(),
  agent_id text not null default '312',
  source_kind text not null default 'manual',
  -- manual | seed | slack | email | yoritoori | obsidian | secondbrain | comm
  topic_text text not null,
  comm_item_id uuid references public.comm_items(id) on delete set null,
  todoist_task_ids text[] not null default '{}',
  todoist_snapshot jsonb not null default '{}'::jsonb,
  status text not null default 'open',
  -- open | decided | skipped
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists task_loop_topics_agent_time_idx
  on public.task_loop_topics (agent_id, created_at desc);
create index if not exists task_loop_topics_status_idx
  on public.task_loop_topics (status, updated_at desc);

create table if not exists public.task_loop_proposals (
  id uuid primary key default gen_random_uuid(),
  topic_id uuid not null references public.task_loop_topics(id) on delete cascade,
  proposal_index int not null check (proposal_index between 1 and 4),
  label text not null,
  body text not null,
  prompt_version text,
  is_starred boolean not null default false,
  created_at timestamptz not null default now(),
  unique (topic_id, proposal_index)
);

create index if not exists task_loop_proposals_topic_idx
  on public.task_loop_proposals (topic_id);

create table if not exists public.task_loop_decisions (
  id uuid primary key default gen_random_uuid(),
  topic_id uuid not null references public.task_loop_topics(id) on delete cascade,
  chosen_index int,
  -- null when none_of_above
  choice text not null,
  -- use | edit_use | none_of_above
  final_text text,
  before_text text,
  after_text text,
  reason_tags text[] not null default '{}',
  free_note text,
  decided_via text not null default 'app',
  -- app | slack
  reflected_todoist_id text,
  history jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (topic_id)
);

create table if not exists public.task_loop_misses (
  id uuid primary key default gen_random_uuid(),
  agent_id text not null default '312',
  -- 312 = 拾い漏れ / 313 = 閉じ漏れ（任意で流用）
  comm_item_id uuid references public.comm_items(id) on delete set null,
  source_ref text,
  entry_kind text not null default 'auto',
  -- auto | weekly_review | user_flag | bancho
  finder_agent text,
  verdict text,
  -- miss | not_miss | pending
  miss_reason_hypothesis text,
  created_at timestamptz not null default now(),
  decided_at timestamptz
);

create index if not exists task_loop_misses_agent_time_idx
  on public.task_loop_misses (agent_id, created_at desc);

create table if not exists public.task_loop_insights (
  id uuid primary key default gen_random_uuid(),
  agent_id text not null default '312',
  kind text not null default 'hypothesis',
  body text not null,
  based_on_ids text[] not null default '{}',
  confirmed boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.task_loop_rules (
  id uuid primary key default gen_random_uuid(),
  agent_id text not null default '312',
  kind text not null,
  -- proposal_prompt | pick_signals | due_rules | done_elsewhere
  body text not null,
  version_label text,
  based_on_ids text[] not null default '{}',
  applied_at timestamptz,
  approved_at timestamptz,
  created_at timestamptz not null default now()
);

alter table public.task_loop_topics enable row level security;
alter table public.task_loop_proposals enable row level security;
alter table public.task_loop_decisions enable row level security;
alter table public.task_loop_misses enable row level security;
alter table public.task_loop_insights enable row level security;
alter table public.task_loop_rules enable row level security;

revoke all on table public.task_loop_topics from anon, authenticated;
revoke all on table public.task_loop_proposals from anon, authenticated;
revoke all on table public.task_loop_decisions from anon, authenticated;
revoke all on table public.task_loop_misses from anon, authenticated;
revoke all on table public.task_loop_insights from anon, authenticated;
revoke all on table public.task_loop_rules from anon, authenticated;

grant select, insert, update, delete on table public.task_loop_topics
  to authenticated, service_role;
grant select, insert, update, delete on table public.task_loop_proposals
  to authenticated, service_role;
grant select, insert, update, delete on table public.task_loop_decisions
  to authenticated, service_role;
grant select, insert, update, delete on table public.task_loop_misses
  to authenticated, service_role;
grant select, insert, update, delete on table public.task_loop_insights
  to authenticated, service_role;
grant select, insert, update, delete on table public.task_loop_rules
  to authenticated, service_role;

comment on table public.task_loop_topics is
  '312 loopware topics (judgment log). Body of utterances lives in comm_items.';
comment on table public.task_loop_decisions is
  'One decision per topic; re-decide overwrites with history.';
