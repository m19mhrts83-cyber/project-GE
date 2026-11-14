-- 58_ 自律化 4合図共通仕様（承認 2026-11-12）段階1: 既存テーブルに共通列を足す
-- 決定2「(A) 既存テーブルに列を足す」。共通テーブルは新設しない。
-- 追加のみ・既定値つき。既存の読み手（317 jarvis_comment_dispatch 等の processed_at 判定）はそのまま動く。
-- 正本: docs/AIエージェントチーム/58_自律化_4合図共通仕様とTodoistイベント検知_草案_20261112.md

-- event_id: <source>:<event_name>:<元のID>（例 todoist:note:added:12345）。重複判定キー
-- Todoist は同じ変更を別 delivery_id で再送しうるので UNIQUE にはせず、317 L1 で「処理済みなら skipped」に使う
alter table public.todoist_webhook_events
  add column if not exists event_id text
    generated always as (
      'todoist:' || event_name || ':' || coalesce(event_data ->> 'id', id::text)
    ) stored;

alter table public.todoist_webhook_events
  add column if not exists kind text not null default 'event';

alter table public.todoist_webhook_events
  add column if not exists status text not null default 'new';

alter table public.todoist_webhook_events
  add column if not exists claimed_by text;

alter table public.todoist_webhook_events
  add column if not exists attempts integer not null default 0;

alter table public.todoist_webhook_events
  add column if not exists last_error text;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'todoist_webhook_events_kind_chk'
  ) then
    alter table public.todoist_webhook_events
      add constraint todoist_webhook_events_kind_chk
      check (kind in ('human', 'schedule', 'event', 'watch'));
  end if;
  if not exists (
    select 1 from pg_constraint where conname = 'todoist_webhook_events_status_chk'
  ) then
    alter table public.todoist_webhook_events
      add constraint todoist_webhook_events_status_chk
      check (status in ('new', 'claimed', 'done', 'failed', 'skipped'));
  end if;
end $$;

-- 既に処理済みの行は done にそろえる（processed_at が正本のまま）
update public.todoist_webhook_events
  set status = 'done'
  where processed_at is not null and status = 'new';

create index if not exists todoist_webhook_events_event_id_idx
  on public.todoist_webhook_events (event_id);

create index if not exists todoist_webhook_events_status_idx
  on public.todoist_webhook_events (status, created_at)
  where status in ('new', 'claimed', 'failed');
