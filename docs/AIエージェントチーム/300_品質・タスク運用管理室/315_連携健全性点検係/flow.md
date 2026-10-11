# フロー — 連携健全性点検係（315）

- FlowForge（設計図）: [flow_zYjp6A4HDURefJhSm0h_zUtX](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_zYjp6A4HDURefJhSm0h_zUtX)
- **実行エンジン（本線）**: GitHub Actions `ops-health-315.yml`
- 実装CLI: `scripts/jarvis_ops_health_315.py`

## きっかけ（確定 2026-10-11）

| 種別 | 正 |
|---|---|
| **本線・時間** | **毎週日曜 21:00 JST** — GHA cron（UTC 日曜 12:00） |
| 副・イベント | WeStudy 週次 GHA の Fail 通知が来たら（人が頼む／パートナー確認ついででも可） |
| 副・手動 | `workflow_dispatch` または Mac で CLI |
| 使わない（本線から外す） | FlowForge 上の曖昧な「21時」プレースホルダ単体／**launchd 日曜 09:15 は本線ではない**（Mac補完用に残置可） |

※ GHA が落ちるとこの週の自動点検は動かない（当面それでよい）。

## ゴール・報告（具体）

| 項目 | 正 |
|---|---|
| **本線の報告先** | Slack **`#ops`**（Webhook `SLACK_WEBHOOK_AI_TEAM_OPS`） |
| **要判断** | Slack **`#consult`** に1行（QR・YAML大量・構造限界の受容） |
| **出さない** | `#report`（業務報告と混ぜない）／「チャットに報告」トグル |
| **1通の中身** | 判定 OK／要フォロー、WeStudy週次結論、オプチャ（cloud時はスキップ明記）、フローURL |
| **ログ** | 社員フォルダ `logs/`（GHAではランログ） |

## 型（Day2どおり）

1. **起動** — GHA 日曜21:00（または手動）
2. **取得** — WeStudy週次チェック（`gh`）。オプチャ詳細は `--cloud` ではスキップ
3. **まとめ** — OK／要フォロー
4. **Slack `#ops`** へ1通

## 最小実装

```bash
# クラウド本線と同じ形（ローカルでも可）
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --cloud --post --mark-checked

# Macでオプチャまで見るとき（--cloud なし）
~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --post --mark-checked
```

GHA: `.github/workflows/ops-health-315.yml`（Secrets に `SLACK_WEBHOOK_AI_TEAM_OPS`）

## 改善ログ（フロー側）

| 日付 | 変更 |
|---|---|
| 2026-10-09 | 型だけ記載 |
| 2026-10-11 | CLI 実装・#ops 報告1通まで（下準備プラン1体目） |
| 2026-10-11 | Phase H: launchd Sun 09:15（のち本線から外す） |
| 2026-10-11 | **本線を GHA 日曜21:00 に確定**。報告＝Slack #ops のみ具体化。`--cloud` |
