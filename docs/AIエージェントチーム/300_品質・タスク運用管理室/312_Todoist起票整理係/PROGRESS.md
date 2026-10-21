# PROGRESS — Todoist起票整理係（312）

作業を再開したらこのファイルを先に読む。

## 2026-10-21 — 運用確認へ格上げ

- registry `status`: 設計中 → **運用確認**（松野「ステータス更新して」）
- ダッシュ: `jarvis_agent_team_status_sync.py` → `agentTeam.json`

## 2026-10-21 — 意図OK（Phase1＋1.5a）

- 受け入れ: 松野「意図オーケー」→ Phase1（digest本線）＋1.5a（ノイズ抑制ルール）を **意図OK**
- 通し create（#consult 番号了承→apply）は運用時任意。必須ゲートではない
- commit: `752024fa`

## 2026-10-21 — Phase 1.5a（ノイズ抑制ルール）

- やったこと: `.cursor/rules/jarvis-chat-open-tasks-312.mdc`。受け入れ済・未完了・最大5・無言create禁止。GenCodeは#ai-hub/inbox経由
- できたもの: ルール＋`chat_open_tasks_inbox.example.md`＋flow/CLAUDE追記
- 次の一手: 1.5b は別了承後

## 2026-10-21 — Phase 1 実装

- やったこと: `scripts/jarvis_todoist_312_digest.py` 追加。SB+GenMail候補→#consult L1投稿。了承後 `--apply --select N` で①create
- できたもの: digest スクリプト・state `todoist_312_digest.json`・初回 #consult 投稿
- 次の一手: 運用で番号了承時に apply。Phase 2 は L2 ボタン

## 2026-10-21 — FlowForge伴走開始

- やったこと: 設計（A/B/C）・flow.md・FlowForge・登録動線①②③
- できたもの: `flow.md` / `CLAUDE.md` / FlowForge URL

## 運用格上げタイミング（確定 2026-10-21）

ノイズ爆発を避けるため、**コード意図OK ≠ すぐ定時自動化**。段階で格上げする。

| 段階 | いつから | 何が「運用」になるか | まだやらない |
|---|---|---|---|
| **A 今すぐ（済）** | 2026-10-21〜 | 1.5a ルール常時（チャット残→L1候補のみ・無言create禁止）。人手／会話で `312_digest` 可 | launchd 定時なし |
| **B ソフト運用** | **2026-10-22（翌朝）〜** | パートナー確認・セッション区切りの**ついで**に digest（`--dry-run` または本投稿）。了承番号だけ `--apply` | 毎日自動投稿しない |
| **C 定時ダイジェスト** | **初回「起票して N」成功の翌日**、または **2026-10-28** の早い方（ノイズ苦情が無ければ） | 週2〜3回 or 隔日の digest→#consult（launchd／GHA どちらか最小） | 毎時・毎日大量は禁止 |
| **D 1.5b** | **C が1週間安定**したあと（目安 **2026-11-04以降**）＋松野了承 | transcripts差分→L1候補 | いきなり全会話スクレイプ |
| **E Phase2/3** | Dのあと、または `#consult` テキスト了承が痛いとき | L2ボタン／材料即時 | C未達で急がない |

**停止**: `#consult` がノイズと感じたら `JARVIS_TODOIST_312_DIGEST_DISABLE=1`（digest／Slack投稿のみ停止。`--apply` は可）。ルール1.5aは残してよい。

## ロードマップ

| Phase | 内容 | 状態 |
|---|---|---|
| 1 | L1ダイジェストを #consult に出し、了承後 create | **意図OK**（2026-10-21） |
| 1.5a | チャット残→L1候補ルール（ノイズ抑制） | **意図OK・運用A**（2026-10-21） |
| 1.5b | transcripts差分→digest | 運用D（了承後） |
| 2 | L2 採用／見送りボタン（116同型） | 運用E |
| 3 | 材料即時トリガー＋定期取りこぼし | 運用E |
