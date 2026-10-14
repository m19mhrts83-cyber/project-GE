# フィードバック返送係

ID: **414**。部門: ミックス・取捨判断室（400）。  
ビルダー／Grok混成プラン由来の**候補**。手順・権限・報告を埋めてから Flowforge／運用に進む。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_y_dlQIKJ1HHXApQeHD8pBaov](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_y_dlQIKJ1HHXApQeHD8pBaov)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図（あれば）: [`flow.md`](./flow.md)

## 1. 役割

- やること: 採用結果をoutbox/Todoist/エージェントflowへ戻す文言を作る
- やらないこと: 対外送信の実行／秘密の再掲／同じ仕事の両系統フル自動化

## 2. 動き出す合図（4種のいずれか）

- [ ] 人が頼む
- [ ] 時間（スケジュール）: （週次ミックス想定）
- [ ] 何かが届いたら（イベント）: Grok inbox／社員報告
- [ ] 変化・失敗を見回ったら:

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | Drive inbox／Todoist／ハブMD |
| 外部連携（API/MCP） | △ | 読取中心 |
| CLI | ○ | inbox poll／Todoistコメント等（送信ゲートは守る） |
| ブラウザ | △ | |
| 画面操作 | × | |

**秘密**: このフォルダの `.env`（キーは `.env.example`）。追加・変更は必ず `~/git-repos/.env.jarvis_private` にも同期。  
**人が確かめる**: 採用／却下の最終、対外送信、金・削除。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 完了報告 | Slack `#report` |
| 要判断 | Slack `#consult` |
| Webhook | env キー名のみ |

## 5. 成果物の置き場

- 比較表・取捨ドラフト: このフォルダ `logs/` または `20_outbox_to_grok/`
- 正本方針: `docs/AIエージェントチーム/03_Grok混成_ミックス運用_20261009.md`

## 6. 作業手順（チェックリスト）

1. 材料を集める（Grok／AIチーム）
2. 差分または提案を1枚にまとめる
3. Slack に報告（人が採用を確定）
4. 必要なら outbox／Todoist へ返送文言

## 7. 改善ログ

| 日付 | 内容 |
|---|---|
| 2026-10-09 | Phase B スタブ作成（ID 414）。tool_fit=A |
