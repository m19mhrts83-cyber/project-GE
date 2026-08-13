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

---

## 資金移動・カード引落バッファ QA（2026-08-14）

| 項目 | 結果 |
|---|---|
| kind `card_settlement_buffer` | DB migration 適用済み＋UI プレイブック |
| P0 ギャップ表示 | 「SMBC不足（寄せの目標）」と明示。銀行＋現金合計を併記 |
| P0 引落日 | フォーム必須＋API で consulting 時必須 |
| P0 二重作成 | 同一 `due_date` の open 案は再利用 |
| P1 引落口座 | `smbc_kariya`（三井住友銀行 刈谷）1本固定。Oliveカード口座は合算しない |
| P1 schema | `schema.sql` 注記＋旧 migration の kind 一覧を同期 |
| 本番 | `/money-ops` にプレイブック表示（本コミット deploy 後） |

**Phase B（運用）**: Vpass 確定額・引落日を入れて寄せ計画→承認→**手動**振込→done。自動振込なし。

### カード引落アラート（2026-08-14）

| 項目 | 結果 |
|---|---|
| スクリプト | `scripts/jarvis_card_debit_watch.py`（Gmail m19m・Vpass お支払い金額のお知らせ） |
| Infinite 本線 | 通知検知 → state / `sync_meta.card_debit_watch_summary` → ホーム Next Action |
| 他カード | 金額≥30万のみアラート（金額なし通知は記録しない） |
| 状況ウォッチ | `card_debit_watch`（年会費 `card_annual_fee` と分離） |
| `/money-ops` | `?due=&need=` および sync_meta からプレフィル |
| 備考 | 既定の Vpass メールは**金額非表示**のため、確定額は `--set` またはフォーム手入力 |

受け入れ: Infinite の 8月通知で引落目安 2026-08-26 が入り、金額未確定のまま warn（T−14内）→ `/money-ops` 誘導。
