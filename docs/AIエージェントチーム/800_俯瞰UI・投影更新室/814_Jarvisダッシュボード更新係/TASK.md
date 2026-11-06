# TASK — 814 Jarvisダッシュボード更新係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | kamiooya-history-edit-20261101 |
| agent_id | 814 |
| executor | codex |
| status | done |
| started_at | |
| finished_at | |

## 依頼

Dashboardの履歴画面から時間の訂正・作業記録の追記を可能にする。旧記録と訂正理由を保持し、エージェントと画面の同時更新を失わず双方向同期する。

## 完了条件

- [x] `/kamiooya/history` に追記・時間訂正・質問回答フォームと認証済み保存を追加
- [x] 同時追記・訂正・入力検証についてNode/Pythonテストを追加
- [ ] 必要なとき Slack `#report`／`#consult`／`#ops` に報告

## 成果物

- OneDrive `P806_神大家AI推進/工数管理/work_history.json` とJarvis Supabaseを履歴IDでマージ。公開画面の保存確認結果は案件履歴の `manual-edit` 項目へ記録する。

## メモ・障害

- 個別案件データはGitに保存しない。既存未追跡 `kiso_course_whisper.json` は変更しない。公開画面の確認結果は案件履歴へ追記する。

## 追加案件 2026-11-06: Q&A効率化の仕上げ点検

- task_id: kamiooya-efficiency-audit-20261106 / executor: codex / status: done
- 依頼: 品質を落とさず待ち時間・AI使用量を減らす追加改善を実装し検証する。
- 完了条件: 依存関係のない待ち合わせを削減し、根拠選択・モデル入力が変わらない統合テスト、結果と残る提案を文書化。

- 結果: 独立取得を前倒し、LINE取得失敗時の不完全生成を抑止。Node76/Deno3/Edge型チェック成功。旧mainでは新しい回帰試験2件が失敗することも確認。PR #242。
