# GHA 手動1回で #ops 到達を確認する

目的: 日曜 cron を待たず、クラウド本線（`ops-health-315.yml` → `jarvis_ops_health_315.py --cloud --post`）が動くことを1回確かめる。

## あなたがやること（画面）

1. Slack でチャンネル **`#ops`** を開く
2. 過去に「連携健全性点検係（315）」の投稿があるか見る（Mac初回分があればOK）
3. Jarvis に **「GHA手動OK」** と返す（こちらで `workflow_dispatch` を実行する）
4. 数分後、`#ops` に **新しい** 315報告が来るか見る  
   - 本文に `起動: GHA ops-health-315` と `オプチャ: スキップ(cloud)` があること
5. 来たら **「#ops 届いた」** と返す

## Jarvis がやること（了承後）

- `gh workflow run "Ops Health 315"`（または同等）
- run の success／fail を短く報告
- 失敗時は Actions ログ要約のみ（秘密・トークンは出さない）

## 成功の目安

| 項目 | OK |
|---|---|
| Actions | Ops Health 315 が緑 |
| Slack `#ops` | 新規1通・cloudスキップ明記 |
| 状態 | まだ **運用確認** のまま（運用へは上げない） |

## 失敗しやすい点

- Secret `SLACK_WEBHOOK_AI_TEAM_OPS` が空 → 本文はログのみ・Slack未投稿（workflow は警告付きで成功しうる）
- WeStudy チェックだけ Fail → `#ops` に「要フォロー」で届く（それで正常）
