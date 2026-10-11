# Phase K — Grok報告→Slack ＋ AI間ミックスアップ

- 確定日: 2026-10-11（併存開始）
- Todoist: `6hj2ghJv7j7Mvp8v`
- 土台: [`17_Grok定型報告_Slack_20261010.md`](17_Grok定型報告_Slack_20261010.md)

## 受け入れ（K）

| 段階 | 内容 | 状態 |
|---|---|---|
| K1 | Slack を Grok 定型の受け皿に | ✅ Webhook＋`action: slack_report` |
| K2 | ホーク／部長 paste に Slack 並立1節 | ✅ 既存（参謀・部長 paste） |
| K3 | エージェント報告と並べて取捨（400室） | ✅ 運用手順を下記に固定（手動ループ開始可） |
| K4 | 重要サマリを Todoist/04 へリンク | ✅ 本MD＋04履歴 |

やらない: Grokチャット廃止。秘密・対外は Jarvis ゲート。

## ミックスアップ（Slack上の型）

```
Grok定型 → #report（【Grok定型報告】）
AI社員自律 → #report / #ops
要判断 → #consult
        ↓
週1またはパートナー確認ついで
411材料 → 412比較 → 413取捨（Jarvis）→ 414返送
```

| ch | 誰が上げる | 松野の見方 |
|---|---|---|
| `#report` | Grok定型 ＋ 業務系社員 | できたこと・見どころ |
| `#ops` | 315 / 814 / 815 等 | 健全性・鮮度 |
| `#consult` | Grok要ボス ＋ 413取捨 | 判断だけ |

## コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_grok_slack_report_apply.py --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_bucho_inbox_poll.py   # slack_report も自動
```

無効化: `JARVIS_GROK_SLACK_REPORT_DISABLE=1`

## サンプル（経路確認用）

inbox に `action: slack_report` の MD を置けば投稿される。  
検証日: 2026-10-11（Jarvis がサンプル1通で経路確認）。
