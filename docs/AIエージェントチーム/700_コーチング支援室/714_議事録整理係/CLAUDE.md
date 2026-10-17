# 714 議事録整理係

ID: **714**。コーチング支援室。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: 未作成（[`flow.md`](./flow.md) が当面の正）

## 1. 役割

- やること: 新規録音のスキャン → Notion 残し候補の提案 → 了承後に Inbox 子ページ＋ Obsidian 1行索引。Action Items は `jarvis_todoist_sb_propose` に委譲。
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

## 7. 改善ログ

| 日付 | 内容 |
|---|---|
| 2026-10-17 | 新設。Stage A/B 実装 |
