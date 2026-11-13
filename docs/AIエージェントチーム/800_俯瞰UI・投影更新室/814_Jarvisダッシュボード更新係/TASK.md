# TASK — 814 Jarvisダッシュボード更新係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | obsidian-bidirectional-20261112 |
| agent_id | 814 |
| executor | codex |
| status | running |
| started_at | 2026-11-12 |
| finished_at | |

## 依頼（2026-11-12追加）

ChatGPTからMac正本Obsidian Vaultを安全に検索・抜粋できる読み取りAPIを実装し、既存日次レビュー保存経路と権限を分離する。Mac heartbeatとSlack #opsのoffline/recovery通知も実装する。

## 完了条件

- [x] allowlist配下のMarkdownだけを検索・抜粋するread-only要求・応答キューを実装
- [x] ChatGPT read toolとMac poll/responseを別キーで認証
- [x] Mac heartbeatを記録し、GAS監視から状態遷移時だけSlack #ops通知
- [x] 既存レビュー保存のローカル正本・no-clobber・OGD同期を維持
- [x] 運用手順・Secrets/手動設定/未デプロイ事項を文書化
- [x] 実装結果をworktreeで確認し、TASKをdoneにしてロック解放

## 実装結果（2026-11-12）

- 追加対応中: PR #379はmainへmerge済み。Supabase migrationとVercel Production秘密変数を設定し、Site plugin version 3を公開。LaunchAgent付け替え・GAS Script Properties/trigger設定・live確認が残る。ブラウザー操作はWork設定で無効。

- 読取MCP、Mac側allowlist検索、短期Supabase要求箱、専用鍵、heartbeat/watchdog/Slack状態通知を追加。LaunchAgentは既存負荷を保つ60秒間隔とした。
- Supabase migration適用、Vercel本番設定、Site plugin更新済み。GitHub PR ChecksとPreview buildは成功。Slack通知・Vault書込み・live検索要求は未実施。
- 運用・残手順: `docs/Obsidian日次レビュー受信.md`。Google Apps ScriptはUI操作でScript Properties/triggerを登録する必要あり。現在のLaunchAgentは一時worktree参照のまま。

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

## 月別Journal保存（2026-11-13）

- task_id: obsidian-monthly-journal-20261113 / executor: codex / status: running
- 目的: `★Journal/YYYY-MM/YYYY-MM-DD.md` に生ログと戦術レビューを1件として保存。対象日から月を決め、競合時は停止。Drive直接uploadを呼ばず、既存Obsidian同期に任せる。
- 完了条件: 月跨ぎ・再送・競合を検証、APIの新旧receipt対応を本番反映、11/12統合ノートを上書きなしで作成。旧2ファイルは保持。
