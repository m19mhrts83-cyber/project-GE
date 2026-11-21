# 714 議事録整理係

ID: **714**。コーチング支援室。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [共有](https://flowforge-259747770348.asia-northeast1.run.app/share/HI4KOYwORPb7ZG1d)（flow_q41qaFFwQ_pX4m6qg04oLb3H）

## 1. 役割

- やること: 新規録音のスキャン → Notion 残し候補の提案 → 了承後に Inbox 子ページ＋ Obsidian 1行索引。Action Items は `jarvis_todoist_sb_propose` に委譲。
- 仕上げ: Notion に載せる議事録は、全エージェント共通の [`52_議事録のまとめ方`](../../52_議事録のまとめ方_20261029.md) で仕上げてから載せる。チャットへの返しは従来どおり3行要約＋宿題
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
| 2026-10-29 | 議事録の型に従う一文を追加（正本は共通の `52_議事録のまとめ方`、Notion に残す議事録すべてが対象、松野さん了承） |
| 2026-10-17 | Builder 組織図反映確認（コーチ・俯瞰室・共有 `uksxiDIzE1AEckKH`・38体） |
| 2026-10-17 | `flow.md` を614型に拡充（人了承ゲート明示）。FFノードは次波 |
| 2026-11-15 | 松野さん依頼で手動整理（Claude Code）。所要45分〜4時間の録音を会議候補とし、既存Notionと突合して未登録5件を52_の型で作成。置き場は内容別（互助会／DB_マサハル／子供コーチング中学校説明会）。家族会議は除外。社内業務電話（10/6）は本人了承後に電話・面談 _Inbox へ（計6件）。state `saved` に記録 |

## 714→312（2026-11-22承認）

議事録整理と本人TODO抽出を同時に行い、Notion保存成功後だけ312へ。Notion了承と起票了承は別。起票はSlackで候補ごとの了承が必要。既存の朝更新は未配送候補だけを回収。手順・入力契約・停止・復旧・検証境界は [保存済み議事録から312へ](docs/saved-minutes-to-todo.md)。過去の保存済み会議は自動配送しない。

本人の呼び方と会議別話者対応はignore済み config/meeting_owner.private.json が正本。未確認の名前・一人称・役職・話者番号を推測で本人にしない。確認済みの他人は除外し、判断理由・設定版を候補に記録する。
