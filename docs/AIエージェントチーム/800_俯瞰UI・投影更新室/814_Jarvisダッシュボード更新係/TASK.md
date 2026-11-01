# TASK — 814 Jarvisダッシュボード更新係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | kamiooya-work-history-20261101 |
| agent_id | 814 |
| executor | codex |
| status | done |
| started_at | |
| finished_at | |

## 依頼

神大家運営の作業項目を事前に相談・設定し、項目別の実行履歴、本人への質問と回答、時間の根拠を記録。本人用Dashboardから案件・項目別に振り返れるようにする。

## 完了条件

- [x] `/kamiooya/history`、項目別記録CLI、運用docsを追加
- [x] Dashboard build、Nodeテスト22件、Pythonテスト2件成功
- [ ] 必要なとき Slack `#report`／`#consult`／`#ops` に報告

## 成果物

- PR #206。正本OneDrive `P806_神大家AI推進/工数管理/work_history.json` と自動生成MD。Jarvis Supabaseへ初期データ投影済み。

## メモ・障害

- 個別案件データはGitに保存しない。既存未追跡 `kiso_course_whisper.json` は変更しない。公開画面の確認結果は案件履歴へ追記する。
