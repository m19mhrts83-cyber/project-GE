# TASK — 313 タスク処置係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | （Todoist id または run_id） |
| agent_id | 313 |
| executor | cursor / claude_code / gencode / launchd / gha / … |
| status | queued |
| started_at | |
| finished_at | |

## 依頼

（何をするか。入力は `input/` または外部パス）

## 完了条件

- [ ] 期待する成果物が `output/`（または記した外部パス）にある
- [ ] `tests/` のチェックを通す
- [ ] 必要なとき Slack `#report`／`#consult`／`#ops` に報告

## 成果物

- 

## メモ・障害

- 2026-11-24 週の整理に一本化（金曜 20:00・A 済みました／B やめる提案）。初回本番は 2026-11-27（金）20:00。launchd 入れ替えは Mac main 追従後にラス隊長（手順は PROGRESS.md）。詳細は CLAUDE.md §0

- 2026-11-22 状態時刻ずれ（旧 digest.json が 11/07 止まり）と同じ候補の繰り返しを修正。「残す」は `cleanup.py --keep N`。詳細は CLAUDE.md 改善ログ
