# 調査メモ — Cursor／GenCodeチャットから残タスクを拾う（2026-10-21）

312 Phase1.5 候補。実装前の方針メモ。

## やりたいこと

- Cursorチャット・GenCode（FRIDAY）チャットを定期確認
- Planで検討した／すぐ終わらない宿題を Todoist（312動線）へ
- 無言の大量 create はしない（既存 L0/L1/L2 と整合）

## ベストプラクティス（Web・要約）

出典の要点のみ（詳細は各URL）。

| 原則 | 内容 | 出典 |
|---|---|---|
| **提案≠タスク** | AIが言っただけでは未確定。ユーザーが受けたものだけ「accepted」 | [NewPrompt: Extract Action Items](https://newprompt.net/guides/extract-action-items-from-an-ai-conversation) |
| **証跡引用** | 各候補に受け入れ文言の引用。引用できないなら起票候補にしない | 同上／[OpenClaw risk](https://openclawdocs.com/use-cases/openclaw-meeting-notes-action-items/) |
| **完了済みを再起票しない** | チャット内で「実装した／結果出した」は completed。Todoistに載せるな | NewPrompt |
| **Inbox／レビュー経由** | 自動直入れより「レビュー用inbox→人が昇格」。スプロール防止 | [Voice→Todoist](https://convertaudiototext.com/blog/transcription-and-todoist) |
| **出典リンク** | タスク説明に元チャット／transcriptへの参照 | 同上 |
| **確認してから書く** | Todoist MCP／Claude連携も「変更は確認後」が公式注意 | [Todoist×Claude](https://www.todoist.com/help/todoist/todoist-and-ai/use-todoist-in-claude-ANlg7v13q) |
| **ドラフト→Confirm** | Slack等で Confirm/Reject してから本番タスク化 | [Meeting→tasks](https://www.mymobilelyfe.com/artificial-intelligence/turn-meetings-into-action-automating-action-item-extraction-and-task-assignment-with-ai) |
| **構造化抽出** | 要約ではなく JSON/表（Action, Status, Owner, Evidence） | Galileo要約ガイド／NewPrompt |

## この環境で取れる／取れない

| ソース | 読取現実 | メモ |
|---|---|---|
| **Cursor Agent** | **可**。`~/.cursor/projects/…/agent-transcripts/*.jsonl`（＋compaction） | ローカル。定期スキャン向き |
| **Cursor 手動Export** | 可だが手作業。tool出力が欠ける事例あり | [Forum](https://forum.cursor.com/t/transcripts-no-longer-exported-in-full/150214) |
| **cursor-history CLI** | コミュニティツールで横断export可 | [S2thend/cursor-history](https://github.com/S2thend/cursor-history) |
| **GenCode チャット本体** | **公式のローカル全文APIは未確認**。Meshログ／Slack `#ai-hub`／Drive outbox が現実的 | FRIDAY運用はSlack＋Driveが正寄り |

## 推奨設計（1本）

**「チャット残タスク → 312 L1ダイジェスト（#consult）」に合流。createは了承後だけ。**

```text
Cursor transcripts（差分）
GenCode側: #ai-hub / inbox MD / FRIDAY完了報告の穴
        ↓ 抽出（acceptedのみ・証跡・未完了）
   312 digest 候補（最大7・L1）
        ↓ #consult（見るだけ）
   了承番号 → ① create-task
```

### ルール層（即効・コード少）

| ルール | 内容 |
|---|---|
| Plan閉じ時 | 未完了TODOを `312` 向け候補ブロック（または inbox MD）に書く。無言create禁止 |
| 「すぐ終わらない」 | セッション内未完なら Todoist候補（L1）へ回す合図を必須化 |
| GenCode/FRIDAY | 残宿題は `#ai-hub` か Drive inbox に1行。チャットだけに閉じない（既存38_と整合） |

### 定期層（後続）

| 項目 | 案 |
|---|---|
| 頻度 | 日1〜2回 or パートナー確認ついで（クレジット節約） |
| Cursor | `agent-transcripts` の mtime 差分のみ LLM抽出 |
| GenCode | `#ai-hub` 既読差分＋inbox MD（チャット直読はPhase後回し） |
| 出口 | 既存 `jarvis_todoist_312_digest.py` に `--from-chats` を足す |

### やらない（当面）

- 全チャット全文の毎回フルLLM（高い・ノイズ）
- 無言の一括 create
- GenCode UI のスクレイピング前提

## Phase 切り方（案）

| Phase | 内容 |
|---|---|
| **1.5a** | Cursorルール：Plan／長い作業の終わりに「残タスク候補」を必ず出す → 人手で312へ |
| **1.5b** | transcripts差分 → 312 digest に自動載せ（L1・#consult） |
| **1.5c** | GenCodeは `#ai-hub`／inbox 経路を公式化（チャット直読は様子見） |

## 採否（2026-10-21）

- **採用**: 推奨どおり 1.5a → 1.5b。ノイズ爆発を明示懸念
- **1.5a 実装済**: `jarvis-chat-open-tasks-312.mdc`（受け入れ・証跡・最大5・無言create禁止）
- **1.5b**: 未着手（transcripts差分→digest）。別了承後
