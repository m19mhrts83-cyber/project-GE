# TASK — 318 Todoist消化係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | orca task_1588877e6c3e（Phase 1 実装） |
| agent_id | 318 |
| executor | claude_code（Miss Lemon・Orca worker） |
| status | done（PR レビュー待ち。マージはラスカルが松野さんの了承後） |
| started_at | 2026-11-23 |
| finished_at | 2026-11-23 |

## 依頼

Phase 1 実装（読むだけ・抽出・変化なし除外・3分類・内部ログ・手動実行）。設計の正本は FlowForge flow_HMy15MUxWiSpw5QgAPYa_8e4（承認済み）。

## 完了条件

- [x] 開始チェック（停止スイッチ・排他・Todoist 接続・本人権限・60分・5件）。不成立は処理せず理由を記録
- [x] 1-1 採用済み基準・判断履歴の読込（313 の指紋照合を再利用・取得失敗は安全停止）
- [x] 1-2 抽出（313 の順位付けを直して再利用・読取失敗は失敗終了・最大5件）
- [x] 1-3 変化なしの除外（件数・理由を内部ログへ・判断不能は保留）
- [x] 1-4 3分類（根拠・迷ったら②・大規模は印だけ）。AI 分類は Claude Code 実行内（追加 API なし）
- [x] 内部ログ（.jarvis_state/todoist_318/・保存失敗は正常完了にしない）と判定・報告案の保存
- [x] テスト `scripts/tests/test_todoist_318_triage.py`、実データで手動実行（読むだけ）
- [x] Todoist 書き込み・Slack 送信・定期起動の登録なし

## 成果物

- `scripts/jarvis_todoist_318_triage.py`
- `config/todoist_318_criteria.yaml`
- `scripts/tests/test_todoist_318_triage.py`
- このフォルダの `CLAUDE.md`・`PROGRESS.md`・`flow.md`

## メモ・障害

- 手動実行の結果は `PROGRESS.md`（件数だけ）
