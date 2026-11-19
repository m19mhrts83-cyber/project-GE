# ★AIエージェントチーム（Drive 写し）

このフォルダで作業するAI（Claude Code・Codex・Orca上のエージェント）向けの案内。
ここは Google Drive に置いた**閲覧用の写し**。プログラムと指示書の正本は Mac の `~/git-repos` にある。

## 正本の場所

| 対象 | 正本（ここを直す） |
|---|---|
| ハブ指示（全ツール共通ルール） | `/Users/matsunomasaharu2/git-repos/docs/AIエージェントチーム/CLAUDE.md` |
| 社員フォルダの指示・TASK・flow | `/Users/matsunomasaharu2/git-repos/docs/AIエージェントチーム/NNN_名前/` |
| 登記簿・索引 | 同 `agents_registry.yaml`・`00_チーム索引.md` |
| プログラム（同期・投稿・定期実行） | `/Users/matsunomasaharu2/git-repos/scripts/` |
| 権限・合図・Slack 設定 | `/Users/matsunomasaharu2/git-repos/config/` |
| ほかのAIからの引き継ぎ | `/Users/matsunomasaharu2/git-repos/agent-handoff/` |

作業前に、上のハブ指示を読んで従う（Claude Code は下の取り込みで自動で読む）。

@/Users/matsunomasaharu2/git-repos/docs/AIエージェントチーム/CLAUDE.md

## このフォルダの扱い

- **文書・設定・プログラムはここで直さない。** 写しは片方向で、ここを直しても git に戻らず、次の同期（毎日 6:10）で上書きされる
- 写しているのは `scripts/jarvis_agent_team_status_sync.py` と `scripts/jarvis_agent_team_drive_sync.py`
- 直したいときは `~/git-repos` の worktree（Orca の作業スペース）で直し、PR → main に入れる。`~/git-repos` の main で直接作業しない
- Drive にしか無いもの（社員フォルダの `outbox/`・`data/`・`logs/` など）は同期で消えない。これらは Drive 側が正
- 番号付き設計MDは `90_ハブ文書/`、ルール類は `91_ルール/` に写してある。git では `docs/AIエージェントチーム/` 直下なので、ハブ指示の中の相対リンクはこのフォルダではそのまま開けない。git 側のパスで読む
- 「名前 2.md」のような同期衝突ファイルは消さずに知らせる（正は git）

## メモリ

Claude Code のメモリは `~/git-repos` で開いたときのもの:
`/Users/matsunomasaharu2/.claude/projects/-Users-matsunomasaharu2-git-repos/memory/MEMORY.md`。
このフォルダから作業するときもここを読み、追記もここにする。

## 守ること

- 秘密（`.env` の値・トークン・パスワード）はこのフォルダ・MD・Slack に書かない
- 対外送信・振込・削除・課金変更は松野さんの了承まで実行しない
- 運用状態（`status`）の変更は先にチャットで提案し、了承後に git の registry を直して同期スクリプトで写す

## 応答

日本語。松野さん向けの説明は専門用語を避け、短く。
