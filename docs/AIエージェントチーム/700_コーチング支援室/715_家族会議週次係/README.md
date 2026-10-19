# 【運用確認】715 家族会議週次係

日曜の家族会議後に、議事録と週次インフォを Notion の当日ページへ入れる係。

- 正本: [`CLAUDE.md`](./CLAUDE.md)
- フロー: [`flow.md`](./flow.md)
- 設定: [`config/family_meeting_weekly.yaml`](./config/family_meeting_weekly.yaml)

## 30秒

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
export PATH="$HOME/.local/bin:$HOME/.genspark-tool-cli/bin:$PATH"

# 予行（書き込みなし）
~/selenium_env/venv/bin/python scripts/friday_family_meeting_weekly.py --dry-run --date 2026-10-25

# 本番（通常は launchd）
~/selenium_env/venv/bin/python scripts/friday_family_meeting_weekly.py --date 2026-10-25

# 失敗の拾い直し（月曜07:00 launchd と同じ）
~/selenium_env/venv/bin/python scripts/friday_family_meeting_weekly.py --retry
```

## 前提

- 松野さんが当日 `(YYYY/MM/DD)` の Notion ページを前週複製で用意している
- NotebookLM は admin・「家族会議」1ノート固定
- 順番は必ず **インフォ → 議事録要約**
