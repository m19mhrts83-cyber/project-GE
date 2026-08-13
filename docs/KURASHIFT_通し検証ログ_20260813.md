# KURASHIFT 通し検証ログ（2026-08-13）

本番: https://jarvis-trade-desk.vercel.app/  
手法: HTTP 煙テスト＋DB 件数＋**ログイン目視（本ログ後半）**

## 結果サマリー

| 柱 | 判定 | メモ |
|---|---|---|
| **① 資産** | ✅ 煙OK | `/` `/themes` `/portfolio` `/settings` = 200 |
| **② LP・税** | ✅ 煙OK＋目視 | `/lifeplan` `/roi` `/tax` 表示確認 |
| **③ 不動産** | ✅ 煙OK＋目視 | A/B計/B実/C/D。キャラメル合算金利 **2.55%**、DSCR 1.33× |
| **買い進めデータ** | ✅ | versions=7（canonical 251124） |
| **財務実績年次** | ✅ | txns 2016–2026 あり |
| **案件ファネル** | ✅ | info→viewing を1件実施（`b3d4dff7-…`）。画面 **情報14 / 内見19** |

## ルート煙

| code | URL |
|---|---|
| 200 | `/` `/themes` `/portfolio` `/lifeplan` `/roi` `/tax` |
| 200 | `/realestate` `/buy-plan` `/deals` `/properties` `/finance-pack` `/settings` |

## ログイン目視（2026-08-13 実施）

| 項目 | 結果 |
|---|---|
| ホーム KPI | HQ・資産合計・LP ペース差・週次 `bloomo_zaim` 失敗表示あり |
| キャラメル 2.55% | `/realestate/properties` 合算金利表・ローン行に **2.55%**（諸費用は 2.675%） |
| 案件1件 | DB で info→viewing。UI カウンタ 15/18 → **14/19** |
| `/lifeplan` | 生涯CF 表示・版差分あり |
| `/roi` | 物件・金融 ROI 表表示 |
| `/tax` | 個人暦年／法人5月期分離・弥生CSV／大野さん取込ボタン |
| Zaim live | API は `ui_confirmed` ゲート済み。予算編成に **確認付き本番ボタン**を追加（デプロイ後にクリック可）。誤射防止のため本番キューは未実行 |

## 実装フォロー（同日）

- `/lifeplan/budget` … Zaim dry-run / 本番（`requireConfirm`）
- `/realestate/buy-plan` … 改訂モード（評価／年次／運営相談）
- `/realestate` … ③-A `re_revise_plan` dry-run／確定
- Next Action 深化・テーマ承認のスマホ押しやすさ・Lab 立花ゲート掲示

## 完了扱い

上記目視＋煙で `verification-with-user` / `wave2-re1` は閉じる。健美家フィードは Phase C 対象外のまま。
