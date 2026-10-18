# Grok材料取込係

ID: **411**。部門: ミックス・取捨判断室（400）。  
ビルダー／Grok混成プラン由来の**候補**。手順・権限・報告を埋めてから Flowforge／運用に進む。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_0CETz0AjmFUkUarpofjGHAp0](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_0CETz0AjmFUkUarpofjGHAp0)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図（あれば）: [`flow.md`](./flow.md)

## 1. 役割

- やること: 10_inbox_from_grok / outbox要約を週次・日次で一覧化
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
| 完了報告 | Slack `#consult` |
| 要判断 | Slack `#consult` |
| Webhook | env キー名のみ |

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 完了・定型・生存確認 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | 障害・失敗・枠切れ |

`#consult` 末尾: `次: Grokで続行 | Jarvisに依頼 | 人判断のみ` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

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
| 2026-10-09 | Phase B スタブ作成（ID 411）。tool_fit=A |
