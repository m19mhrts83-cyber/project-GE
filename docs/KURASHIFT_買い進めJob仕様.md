# KURASHIFT — 買い進め Job（千三つファネル）仕様

最終更新: 2026-08-13  
対象: Sprint 2 骨格（実装境界の固定）

## 目的

長期目標 **CF 月50万** に向け、条件に合う物件を **情報→内見→買付→融資→購入** で積み上げる。  
「買えない＝失敗」にせず、**件数と転換率**で千三つを可視化する。

## ステータス（`kurashift_re_deals.status`）

| status | 意味 | 千三つ対応 |
|---|---|---|
| `info` | 情報収集・メール候補 | 情報 1000 |
| `viewing` | 内見予定／実施 | 内見 100 |
| `offer` | 買付・交渉 | 引っかかり 10 |
| `loan` | 融資審査中 | — |
| `purchased` | 購入完了 | 購入 3 |
| `passed` | 見送り（学習として残す） | 非失敗 |
| `archived` | 完了アーカイブ | — |

## 供給経路

| 優先 | source | 実装 |
|---|---|---|
| ベース | `mail_admin`（主）＋ `mail_estate`（補完） | dry-run → 候補カード。自動送信なし |
| 追加 | `kenbiya` / `rakumachi` | Sprint 3 |
| 手動 | `manual` | UI／Jarvis |

対外問い合わせは **送信前確認必須**（`jarvis-outbound-confirm`）。

## マッチ入力（買い進め Excel から）

- `kurashift_buy_plan_criteria`（エリア・戸建・利回・価格・土地値・ハザード）
- `kurashift_buy_plan_constraints`（銀行・融資枠・地理条件）
- 現行版: `version_key=251124`（`is_canonical`）

## Q&A 助言

- ソース: `kamiooya-qa`／WeStudy 知識（融資・修繕・空室ヒント優先）
- 保存先: `kurashift_re_deals.advice_json`
- UI: `/realestate/deals` の案件詳細パネル（検索クエリ＝エリア＋構造＋制約キーワード）

## 運営経緯

- 表: `kurashift_ops_consult_events`
- 初回: `809_神大家運営回答/5.やり取り.md` → `scripts/jarvis_kurashift_ops_consult_ingest.py`
- 将来: Gmail admin 主走査＋estate 補完（年次 LP／プラン件名）

## ローン正本

- [借入残高トラッカー](https://loan-tracker-plum.vercel.app/)（Google: **estate**）
- ジョブ案: `re_sync_loan_tracker`（読取投影のみ。Drive 形式調査後）

## Excel export

- 目標: 運営共有用に **STEP3 シート互換** の出力
- 入力: canonical `kurashift_buy_plan_events`
- Sprint 2 では「取込→画面表示」まで。export は次イテレーション可

## ジョブ案（worker）

| job_type | 内容 | 危険度 |
|---|---|---|
| `buy_plan_ingest` | Excel 再取込 | 低 |
| `re_mail_match_dry_run` | admin/estate 物件メール候補 | 低（送信なし） |
| `re_deal_advice` | Q&A 注入 | 低 |
| `re_sync_loan_tracker` | ローン投影 | 低（読取） |
| （将来）問い合わせ下書き | 送信は別確認 | 高 |

## UI 導線（2026-08-13）

1. **長期プラン** `/realestate/buy-plan` — events 年表・criteria・constraints・Excel Jobs  
2. **今狙う** — 同画面 Focus（Notion 条件＋ Excel）  
3. **実行** `/realestate/deals` — 千三つファネル・メール候補  
4. **運用** `/realestate` — CF・DSCR・名義切替（③-A）

編集者向け: [`docs/KURASHIFT_編集者引き継ぎ_不動産AB_20260813.md`](KURASHIFT_編集者引き継ぎ_不動産AB_20260813.md)

- [ ] canonical Excel が DB に入り、イベント件数が 0 でない
- [ ] `/realestate` に CF 月50万 KPI（定義メモリンク）
- [ ] `/realestate/deals` にファネル件数（空でもステータス軸）
- [ ] 運営経緯が1件以上（キーワードヒットがある場合）
- [ ] 自動問い合わせ送信が走っていない
