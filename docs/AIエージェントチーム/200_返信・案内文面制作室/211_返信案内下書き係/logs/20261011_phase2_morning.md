# Phase2 朝便 dry-run — 2026-10-11

## コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_reply_draft_211.py --morning --dry-run
```

## 結果（要約）

| 項目 | 値 |
|---|---|
| engine | heuristic / LLM off |
| unreplied candidates | 29（処理上限8） |
| PM applyable | **0** |
| PM 見積B待ち | **0** |
| PM 古いためスキップ（21日超） | **4** |
| Slack | report skip（起案0・要確認0） |

## 判定ロジック確認

- 管理会社フォルダは `101_`〜`104_` のみ自動起案対象
- 21日超はスキップ（古い候補が4件ヒット）
- 見積B未検出時は `#consult`（今回0件）
- 書込・Slackは `--dry-run` のため未実行

## Phase1 送信クローズ

- ミニテック: Gmail 送信済（別フロー）
- Tcell: LINE 貼付送信済 → `line_clip_send.py --record-only` で `5.やり取り.md` 追記
