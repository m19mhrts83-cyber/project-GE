# 312 PROGRESS

更新: 2026-11-07

## ループウェア実装

- [x] 入口設計 docs／CLAUDE／flow／設計書コピー
- [x] Supabase `task_loop_*` migration（`20261107_task_loop.sql`）
- [x] `apps/loopware` `/312`（S05・シード3・localStorage＋API）
- [x] `prompts/proposal.md`
- [x] 拾い漏れスキャン `jarvis_todoist_312_miss_scan.py`／`/312?tab=misses`
- [ ] 本番 Vercel デプロイ＋Chrome 受け入れ確認（松野）

## 2026-11-09 — 入口を本物に（collect／reflect）

- 背景: Nody /312 のお題・判断20件がすべて見本。Slack の松野さんの発言を拾う入口、新しいお題の3案、決定→Todoist が無かった（確認メモはプロジェクト共有の 312_loopware_review.md）
- [x] `scripts/jarvis_todoist_312_collect.py` collect: #consult／#ai-hub／#report の松野さん本人の発言（AI が同名で出した報告は形で除外）→ 依頼／問いかけ／やりたい話をルールで判定 → 既存 Todoist と照合 → 3案（rule-v1）→ `task_loop_topics`（`source_ref`＝Slack リンク）→ #consult に1通
- [x] reflect: Nody で「既存タスクへ追記」「別タスクを作る」を選んだものだけ Todoist へ（`reflected_todoist_id`）。登録しない・見本は `-` 印
- [x] `.github/workflows/todoist-312-collect.yml`: collect 月・水・金 20:30 JST／reflect 30分ごと（7〜24時）
- [x] Nody: `/api/topics` で本物のお題を見本の前に並べる。★の案を最初から選ぶ。元の発言リンク
- [ ] migration `20261109_task_loop_source_ref.sql` を本番に適用（松野）
- [ ] 初回 collect の候補を松野さんが見て OK → 本運用
- 後回し: 3案を AI で作る（GHA に LLM キーが無いのでまず型）、拾い漏れの週1見直し、Slack 完結
- [ ] 段階3: 単純確定の Slack 完結（ログ十分後）
