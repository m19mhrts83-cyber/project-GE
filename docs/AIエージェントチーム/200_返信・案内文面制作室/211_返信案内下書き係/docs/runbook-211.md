# 211 実行ランブック（朝便・管理会社）

更新: 2026-10-11（Phase3 Graph／GHA）

## 何をする係か（変えない）

管理会社の未返信を拾い、**正本下書きに書く**。知らせは Slack `#report`。送信は人。

## 本線（GHA）

毎日 07:30 JST（`jarvis-reply-draft-211.yml`）:

1. Graph で 101〜104 の `5.やり取り.md` を取得
2. `night_triage --lane partner --skip-fetch`（heuristic）
3. 211 フィルタ（lookback21・見積B・社ごと最新1件・テンプレ下書き）
4. Graph PUT で `4.送信下書き.txt` / `4.LINE送信下書き.txt`
5. 起案あり → `#report`／見積B待ち → `#consult`／失敗 → `#ops`

```bash
gh workflow run jarvis-reply-draft-211.yml -f dry_run=true
gh workflow run jarvis-reply-draft-211.yml -f dry_run=false
# ローカルで同じ経路
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
PYTHONPATH=scripts ~/selenium_env/venv/bin/python scripts/jarvis_gha_reply_draft_211.py --dry-run
```

停止: Secret `JARVIS_REPLY_DRAFT_211_GHA_DISABLE=1`

## 保険（Mac launchd）

`com.matsunoma.jarvis.reply-draft-211`（ローカル OneDrive path）。GHA が安定したら uninstall。

## 実装の正

| 部品 | 場所 |
|---|---|
| GHA エントリ | `scripts/jarvis_gha_reply_draft_211.py` |
| フィルタ＋Slack | `scripts/jarvis_reply_draft_211.py` |
| 正本 PUT | `jarvis_night_triage.apply_draft_to_partner` → `upload_file_graph` |
| Graph | `scripts/jarvis_onedrive_graph.py` |

## 成功の見え方

- OneDrive 上の `4.*送信下書き.txt` が更新されている（Mac スリープでも可）
- 起案時は `#report`、見積B待ちは `#consult`
- 送信されていない
