# KURASHIFT 通し検証ログ（2026-08-13）

本番: https://jarvis-trade-desk.vercel.app/  
手法: HTTP 煙テスト＋DB 件数（ログイン後の数値目視は脇に置き・後続可）

## 結果サマリー

| 柱 | 判定 | メモ |
|---|---|---|
| **① 資産** | ✅ 煙OK | `/` `/themes` `/portfolio` `/settings` = 200 |
| **② LP・税** | ✅ 煙OK | `/lifeplan` `/roi` `/tax` = 200 |
| **③ 不動産** | ✅ 煙OK | A/B計/B実/C/D すべて 200 |
| **買い進めデータ** | ✅ | versions=7（canonical 251124）。deals=36（info15 / viewing18 / passed3） |
| **財務実績年次** | ✅ | txns 2016–2026 あり（年次CF線に利用可） |

## ルート煙

| code | URL |
|---|---|
| 200 | `/` `/themes` `/portfolio` `/lifeplan` `/roi` `/tax` |
| 200 | `/realestate` `/buy-plan` `/deals` `/properties` `/finance-pack` `/settings` |

## 確認待ち（脇置き）

- ログイン後の KPI 数値・キャラメル 2.55% 目視
- 案件1件の draft→内見の体感操作
- Zaim live ボタンの確認 UI クリック

## 次（実施済み）

不動産 CF 年次プロット → `/realestate/buy-plan` に「想定 vs 実績」カードを追加（2026-08-13）。

## 検証で脇置きしたまま（ユーザー確認が必要）

上記「確認待ち」3点。`buy-plan-revise-modes`（年1実績反映／Excel改訂）は検証・相談後。
