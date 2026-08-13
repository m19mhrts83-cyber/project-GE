# Tax YoY 回帰ゲート（2026-08-13）

対象: `/tax` 年度推移・評価（plan `tax_yoy_screen_8eba82d2`）  
DB: `jarvis-dashboard` · `kurashift_tax_year_metrics`（10行シード済）

## ゲート結果

| # | 条件 | 結果 |
|---|---|---|
| 1 | 個人カードは `tax_build_yayoi_csv` のみ | ✅ |
| 2 | 個人に税理士メール取込ボタンなし | ✅（法人カードのみ `tax_ingest_accountant_mail`） |
| 3 | API が personal scope のメール取込を拒否 | ✅ `app/api/jobs/route.ts` |
| 4 | CLI `ingest_mail` は corporate 以外拒否 | ✅ |
| 5 | 弥生 CSV は `register=false` | ✅ `jarvis_kurashift_tax.py` |
| 6 | 個人＝暦年／法人＝5月期で軸分離 | ✅ 見出し「年度推移（暦年）」「年度推移（5月期）」 |
| 7 | Zaim 気配に「確定申告の所得そのものではない」注記 | ✅ |
| 8 | 住民税列なし | ✅ |
| 9 | 税ページに合算CFグラフなし（フッタリンクのみ） | ✅ → `/realestate` |
| 10 | metrics API 認証必須 | ✅ |
| 11 | `tsc --noEmit` | ✅ |

## シード（scope × year）

| scope | fiscal_year | 主な金額 |
|---|---|---|
| personal | 2025 | 課税所得 7,305,000 / 所得税 795,410 |
| personal | 2024…2017 | 複数年（前年差用） |
| corporate | 2025 | 売上 973,104 / 経常 −175,832 / 法人税等 0 |

## 残チケット（本機能外）

- V-2B-EV: 法人 Gmail 取込 0 件調査  
- V-2B-MAP: 弥生マップ拡充  
