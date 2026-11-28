# TASK — 319 アプリ安全点検係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | orca task_a479c0749c31（新設・下書き） |
| agent_id | 319 |
| executor | claude_code（Miss Lemon・Orca worker） |
| status | done（PR レビュー待ち。マージは松野さんの判断） |
| started_at | 2026-11-28 |
| finished_at | 2026-11-28 |

## 依頼（アイテム150）

300 室に 319 を**設計中**で新設する。今回は CLAUDE.md 下書き・流れ図・registry／部門・状態ボードまで。

## 完了条件

- [x] 社員フォルダ（CLAUDE.md・AGENTS.md・TASK.md・PROGRESS.md・flow.md・設計中マーカー）
- [x] 流れ図（番号・主体・実行者・作業・保存・報告・成功／部分成功／失敗・判断点・戻り矢印）
- [x] registry に 319（status 設計中・`flow_confirmed_at` なし）、01_部門.md・00_状態ボード.md・00_チーム索引.md に1行
- [x] 確定／案／未確認を分けて記載
- [x] 実点検・定時実行・権限の発行・KURASHIFT のコード読みはしていない

## 次の実装（松野さんが流れ図を見て了承した後）

1. 頻度・結果の置き場・報告先を決める（PROGRESS.md の表）
2. 置き場が決まったら、1本目（KURASHIFT 内部・軽い点検）を手動で実行
3. 結果を見て、定時化（GHA／launchd）と深い点検の頻度を決める
