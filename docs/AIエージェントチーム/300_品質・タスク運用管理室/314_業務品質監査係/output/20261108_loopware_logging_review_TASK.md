# TASK — Loopware判断ログと週次レビュー接続

## Goal

Loopware 312／313の判断が失われず、314の週次レビューから参照でき、画面上で「判断記録」と「Todoist実処置」を区別できる状態にする。

## Background

Loopware公開UIとリポジトリ実装を2026-11-08に読み取り確認した。312は `task_loop_*`、313は `owner_decisions` を保存先とする。ブラウザ `localStorage` 保存はAPI保存失敗時にも残るため、画面表示だけで共有DB保存を確認できない。314の週次運用は `owner_decisions` を読む想定で、312側ログの集計接続が不明確。313画面の選択はTodoistの実処置を行わず、既存Slack／CLI運用と境界を示す必要がある。

## Confirmed

- Loopware app: `apps/loopware`
- Decision API: `apps/loopware/app/api/decide/route.ts`
- Browser persistence: `apps/loopware/lib/storage.ts`
- 312 schema: `apps/jarvis-dashboard/supabase/migrations/20261107_task_loop.sql`
- 313 schema: `apps/jarvis-dashboard/supabase/migrations/20261107_owner_decisions_loopware_payload.sql`
- 314 review script: `scripts/jarvis_owner_decisions_weekly.py`
- 314 stage 3 script: `scripts/jarvis_loopware_stage3_rules.py`
- Product/role proposal: [`20261108_loopware_banto_hawk_review.md`](./20261108_loopware_banto_hawk_review.md)

## Unknowns to verify first

- Current Supabase migration state and whether production persistence works for each route.
- Whether 312 topic/proposal/decision rows are already consumed by any report besides the identified scripts.
- Whether the 313 UI wording intentionally implies an action or only a decision log.

## Scope

- Inspect existing readers and migrations; verify current contracts before changing schema.
- Ensure 312 and 313 decisions can both be included in the 314 weekly review without silently omitting one source.
- Make database persistence outcome visible or otherwise clearly distinguish local-only records from shared records.
- Make 313 UI wording accurately communicate whether it records a choice or performs a Todoist operation.
- Prevent repeated submissions for the same decision from creating avoidable duplicate topic/log rows; preserve intentional re-decisions/history.
- Add or adjust focused coverage for persistence failure, repeated decision, and weekly aggregation behavior.

## Requirements

- Prefer an additive, backward-compatible solution. Reuse existing tables and weekly review where practical; do not add a parallel decision ledger without a demonstrated need.
- Do not invent production migration status. If migration application is required, provide the SQL and exact deployment prerequisite separately.
- Keep approval boundaries: a Loopware decision record is not approval to complete, delete, reschedule, or create a Todoist task.
- Do not include credentials, personal message bodies, or sensitive source text in logs or reports.
- Follow the existing 312/313 division and Banto/Hawk no-duplicate-work rules.

## Acceptance Criteria

- A 312 decision and a 313 decision are each represented in the 314 weekly review with source, decision, reason tags, timestamp, and stable task/topic reference where available.
- Local-only persistence and shared persistence are distinguishable to the user; API failures are not reported as successful shared saves.
- Re-submitting the same topic decision does not create duplicate records, while an intentional revised decision remains auditable.
- 313 UI text does not imply Todoist changed unless the app actually performed and verified that change.
- Tests or focused verification cover success, persistence failure, idempotency/re-decision, and weekly aggregation.
- No Todoist external mutation, Slack send, or production deploy is performed as part of this task.

## References

- `apps/loopware/README.md`
- `apps/loopware/app/api/decide/route.ts`
- `apps/loopware/components/TaskDedupeClient.tsx`
- `apps/loopware/components/CleanupClient.tsx`
- `apps/loopware/lib/storage.ts`
- `scripts/jarvis_owner_decisions_weekly.py`
- `scripts/jarvis_loopware_stage3_rules.py`
- `docs/AIエージェントチーム/300_品質・タスク運用管理室/312_Todoist起票整理係/CLAUDE.md`
- `docs/AIエージェントチーム/300_品質・タスク運用管理室/313_完了候補確認係/CLAUDE.md`

## Instructions

- This is an implementation handoff only; do not begin before the receiving agent accepts it.
- First inspect the current branch, worktree, and existing changes. Preserve unrelated user work.
- Implement, verify, self-review, then report changed files, checks, migration needs, open questions, and next step.
- Do not modify Banto/Hawk schedules or permissions as part of this task.

## Safety

- No external messages or Todoist mutations.
- No deletion, production deployment, permission changes, or paid operations.
- Keep secrets out of output, docs, logs, and git history.

## Output

- Code changes and focused tests/verification.
- Updated docs if implementation behavior changes.
- Concise completion report for `#ai-hub` after owner review; no Slack message from the implementation task without approval.
