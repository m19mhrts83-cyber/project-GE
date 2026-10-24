# フロー — 業務品質監査係（314）

文字1行: **土曜 9:00 機械チェック（AI なし）→ 9:30 Miss Lemon が今週の変更をレビュー → 修正 PR → 人がマージ**

```mermaid
flowchart LR
  A[土曜 9:00 launchd] --> B[jarvis_weekly_review_314.py<br/>GHA失敗・時刻ずれ・繰り返しエラー・テスト・依存・AI呼出し]
  B --> C[facts_YYYYMMDD.md / latest.json]
  B --> S[Slack #ops or #report]
  C --> D[土曜 9:30 Claude 定期タスク<br/>Miss Lemon＝点検者]
  G[今週の main 差分] --> D
  D --> E[修正（worktree・最大5件）]
  E --> F[PR＋output/週次レビュー.md]
  F --> H[松野がマージ]
  D --> P[人の対応待ち→翌週へ持ち越し]
```

| # | ステップ | 誰 |
|---|---|---|
| 1 | 事実を集める（AI なし） | launchd |
| 2 | 要確認を仕分け・今週の変更を観点別にレビュー | Miss Lemon |
| 3 | 小さく確実なものを直す・テスト | Miss Lemon |
| 4 | PR とレビュー MD | Miss Lemon |
| 5 | マージ・人の対応 | 松野 |

やらないこと: マージ、Slack 投稿（Claude 側）、対外送信、秘密の表示、status 変更。
