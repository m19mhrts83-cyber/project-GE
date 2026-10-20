# PROGRESS — Todoist起票整理係（312）

作業を再開したらこのファイルを先に読む。

## 2026-10-21 — Phase 1.5a（ノイズ抑制ルール）

- やったこと: `.cursor/rules/jarvis-chat-open-tasks-312.mdc`。受け入れ済・未完了・最大5・無言create禁止。GenCodeは#ai-hub/inbox経由
- できたもの: ルール＋`chat_open_tasks_inbox.example.md`＋flow/CLAUDE追記
- 次の一手: 1.5b（transcripts差分→digest）は別了承後。Phase1通しは番号了承待ち

## 2026-10-21 — Phase 1 実装

- やったこと: `scripts/jarvis_todoist_312_digest.py` 追加。SB+GenMail候補→#consult L1投稿。了承後 `--apply --select N` で①create
- できたもの: digest スクリプト・state `todoist_312_digest.json`・初回 #consult 投稿
- 次の一手: 松野が番号了承 → apply で create 確認。Phase 2 は L2 ボタン

## 2026-10-21 — FlowForge伴走開始

- やったこと: 設計（A/B/C）・flow.md・FlowForge・登録動線①②③
- できたもの: `flow.md` / `CLAUDE.md` / FlowForge URL

## ロードマップ

| Phase | 内容 | 状態 |
|---|---|---|
| 1 | L1ダイジェストを #consult に出し、了承後 create | **実装済・通し確認待ち** |
| 1.5a | チャット残→L1候補ルール（ノイズ抑制） | **済** |
| 1.5b | transcripts差分→digest | 将来（了承後） |
| 2 | L2 採用／見送りボタン（116同型） | 将来 |
| 3 | 材料即時トリガー＋定期取りこぼし | 将来 |
