-- 312 入口（jarvis_todoist_312_collect.py）: お題の元発言（Slack パーマリンク等）を持ち、同じ発言を二度お題にしない。
-- 追加のみ（既存の行・列は変えない）。

alter table public.task_loop_topics
  add column if not exists source_ref text;

create unique index if not exists task_loop_topics_agent_source_ref_uidx
  on public.task_loop_topics (agent_id, source_ref)
  where source_ref is not null;

comment on column public.task_loop_topics.source_ref is
  '元の発言（Slack パーマリンク／comm_items:<id>）。同じ発言の再取込を防ぐ鍵';
