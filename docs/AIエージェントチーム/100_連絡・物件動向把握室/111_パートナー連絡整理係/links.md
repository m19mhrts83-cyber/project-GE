# リンク集 — パートナー連絡整理係（111）

やり取り・下書き・添付の**正本は動かさない**。ここは参照用。

## OneDrive 正本（26）

| 用途 | パス |
|---|---|
| パートナー相談ルート | `~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/` |
| やり取り（各社） | `…/26_パートナー社への相談/*/5.やり取り.md` |
| 送信下書き | `…/26_パートナー社への相談/*/4.送信下書き.txt` |
| LINE ハブ下書き | `…/26_パートナー社への相談/LINE送信下書き.txt` |
| 受信添付 | `…/26_パートナー社への相談/*/1.受信添付(Stock)/YYYY-MM-DD/` |
| 連絡先 | `…/26_パートナー社への相談/000_共通/連絡先一覧.yaml` |

Finder:

```bash
open "$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
```

## この係フォルダ

| 用途 | パス |
|---|---|
| 指示 | [`CLAUDE.md`](./CLAUDE.md) |
| フロー | [`flow.md`](./flow.md) |
| 報告文面 | [`report_consult.md`](./report_consult.md) |
| Slack 控え | [`reports/`](./reports/) |
| 人が見る場所 | [`運用メモ_人が見る場所.md`](./運用メモ_人が見る場所.md) |

## 実行入口

| 枠 | 入口 |
|---|---|
| 昼 11:50 | GHA `jarvis-partner-day-report.yml` → `scripts/jarvis_partner_day_pipeline.py` |
| 夜 20:30 | launchd `com.matsunoma.jarvis.partner-111-night` → `scripts/jarvis_partner_night_pipeline.py` |
| 副合図 | 「パートナー確認して」（既存パートナー確認手順） |
| FlowForge | https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_AZNxdNkT5-DNZyL5pK4AMrbj |

## ダッシュボード

| 画面 | URL |
|---|---|
| Jarvis | `JARVIS_DASHBOARD_URL`（未設定時は https://jarvis-dashboard-amber.vercel.app/ ） |
| 815 | `/openchat`（本係 `#report` には載せない） |
