# Phase 1 — 313 L1ダイジェスト → #consult → 了承後 close

対象: 313 完了候補確認係  
所要目安: 1〜2時間（Jarvis側実装＋1回の通し）

## ゴール

オーナー確認列の候補を **見るだけ** の一覧で Slack `#consult` に出し、

- **確認のみ** → `--auto-close-confirm` で Jarvis が close（コメント必須）
- **要判断** → 松野が「閉じて ✅N」→ `--apply --select ✅N`

新規 create はしない（312側）。

## 使うもの

| 道具 | 役割 |
|---|---|
| Todoist API | `lane`／`complete-task` |
| Slack Webhook | `#consult`／`#report` |
| スクリプト | `scripts/jarvis_todoist_313_digest.py` |

## 実装済み（2026-10-21）

- スクリプト・state `.jarvis_state/todoist_313_digest.json`
- 停止 `JARVIS_TODOIST_313_DIGEST_DISABLE=1`
- flow／PROGRESS／CLAUDE 正本

## 通し確認

1. `--dry-run` でオーナー確認が列挙される
2. `#consult` に「【相談】313 完了候補確認」が出る（✅番号・最大5。期日超過は別投稿の📅）
3. 確認のみがあれば `--auto-close-confirm`（dry で先に確認）
4. 要判断は「閉じて ✅N」後に `--apply --select ✅N`

## 運用格上げ

PROGRESS の A〜E（B=10/22、C=初回通し翌日 or 10/28）。
