# 714 議事録整理係

ID: **714**。コーチング支援室。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: 未作成（[`flow.md`](./flow.md) が当面の正）

## 1. 役割

- やること: 新規録音のスキャン → Notion 残し候補の提案 → 了承後に Inbox 子ページ＋ Obsidian 1行索引。Action Items は `jarvis_todoist_sb_propose` に委譲。
- 仕上げ: Notion に載せる議事録は **[`議事録の型.md`](./議事録の型.md) で仕上げてから**載せる（結論・決定・ToDo表を先頭、話者は実名、全文はリンク、A4 1枚目安）。Genspark 要約をそのまま貼らない。チャットへの返しは従来どおり3行要約＋宿題
- やらないこと: 全文常時ミラー、家族会議の Inbox 流用、無言の Notion 作成・Todoist 起票。

## 2. 動き出す合図

- [x] 人が頼む: 「議事録整理して」
- [x] パートナー確認前半のついで（失敗しても止めない）
- [x] 朝オープン相乗り（launchd soft-fail 想定）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | curate / genspark fetch / notion API |
| 秘密 | ○ | `GSK_API_KEY`・`NOTION_API_TOKEN`（jarvis_private） |

**人が確かめる**: Notion に残すかの了承。対外送信はしない。

## 設計4点

| 柱 | 内容 |
|---|---|
| 入口 | Genspark list ＋ JPR 未処理 |
| 確認 | 提案のみ。了承後 apply |
| 履歴 | `.jarvis_state/meeting_minutes_curate.json` ＋ `reports/` |
| 停止 | `disabled` / `JARVIS_MEETING_MINUTES_CURATE_DISABLE=1` |

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 提案 | チャット／必要なら Slack `#report` |
| 正本 | Notion 電話・面談 `_Inbox` |

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 完了・定型・生存確認 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | 障害・失敗・枠切れ |

`#consult` 末尾: `次: Grokで続行 | Jarvisに依頼 | 人判断のみ` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

## 7. 改善ログ

| 日付 | 内容 |
|---|---|
| 2026-10-17 | 新設。Stage A/B 実装 |
| 2026-10-29 | 議事録の型を追加（Notion に残す議事録すべてが対象、松野さん了承） |
| 2026-10-17 | Builder 組織図反映確認（コーチ・俯瞰室・共有 `uksxiDIzE1AEckKH`・38体） |
| 2026-10-17 | `flow.md` を614型に拡充（人了承ゲート明示）。FFノードは次波 |
