# TASK — 715 家族会議週次係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | （run_id / 日付） |
| agent_id | 715 |
| executor | launchd / gencode |
| status | queued |
| started_at | |
| finished_at | |

## 依頼

（通常は launchd 日曜21:30。手動時は対象日を明示）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
export PATH="$HOME/.local/bin:$HOME/.genspark-tool-cli/bin:$PATH"
~/selenium_env/venv/bin/python scripts/friday_family_meeting_weekly.py --date 2026-10-25
```

## 完了条件

- [ ] Drive `13_家族会議_週次/議事録/YYYYMMDD_家族会議_Genspark議事録.md`
- [ ] NotebookLM「家族会議」へ当該週ソース追加
- [ ] Studio インフォ（`★アウトプット/YYYYMMDD_家族会議_週次インフォ*.png`）
- [ ] Notion 当日ページ末尾に「インフォ → 議事録要約」の順で入っている
- [ ] Slack `#report`（失敗なら `#ops`）

## 成果物

- `output/` … 実行メモ（任意）
- 正本は Drive／Notion／`.jarvis_state/friday_family_meeting_weekly.json`

## メモ・障害

- Notion ページ未作成 → 松野さんに前週複製を依頼（自動では複製しない）
- 会議特定が曖昧 → `--meeting-id` で指定
- Studio 枠切れ → 月曜07:00 `--retry` → だめなら FRIDAY 手当て
