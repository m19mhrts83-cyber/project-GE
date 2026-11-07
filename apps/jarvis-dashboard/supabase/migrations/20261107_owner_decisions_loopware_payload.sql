-- 313 ループウェア: owner_decisions の action／payload 契約を拡張（表構造は据え置き）
-- 新表は作らない。コメントとチェック用ビューのみ。

comment on column public.owner_decisions.action is
  'sent/skipped/snoozed/done/create/dismiss/close/reschedule/drop/merge/adopt/skip 等。313 loopware: close=済んだ / reschedule=いつ優先 / drop=やめる(完了+コメント) / merge=寄せ完了';

comment on column public.owner_decisions.payload is
  'jsonb. 313 cleanup: kind, proposals[], starred, reason_tags[], evidence_urls[], suggested_due, chosen_index, n';

-- 314 が読みやすい要約ビュー（service_role）
create or replace view public.owner_decisions_313_loop as
select
  id,
  decided_at,
  action,
  source,
  target_id,
  subject,
  note,
  payload ->> 'kind' as loop_kind,
  payload ->> 'starred' as starred,
  payload -> 'reason_tags' as reason_tags,
  payload ->> 'suggested_due' as suggested_due,
  review_week
from public.owner_decisions
where surface = 'todoist_313';

revoke all on public.owner_decisions_313_loop from anon, authenticated;
grant select on public.owner_decisions_313_loop to service_role;
