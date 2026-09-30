# KURASHIFT — 不動産事業 BS・PL（ファイナンス戦略ゼミ準拠）

**作成日**: 2026-08-24  
**画面**: `/mq?view=re-pl`  
**スキーマ正本**: OneDrive `230_物件調査/★物件調査まとめExcel/★事業計画BS・PL(不動産賃貸).xlsx`

---

## 目的

不動産事業を **一番素直に** 評価するための伝統的 PL / BS。  
MQ要素法・資金繰り・家計BSは置き換えず、役割を分けて見る。

| 画面 | 見るもの |
|---|---|
| **事業BS・PL** | 減価償却・利息・税込みの利益と期末BS |
| **資金繰り** | 現金の月次（元本返済の正） |
| **MQ会計** | PQ/VQ/F/G の構造評価（PLの代替ではない） |
| **家計BS** | 家計全体（事業合計を二重計上しない） |

---

## データ源

| 項目 | ソース |
|---|---|
| 不動産収入・経費 | `kurashift_finance_transactions` ＋事業ホワイトリスト |
| 利息・元金・残債 | `kurashift_loan_tracker_loans` |
| 建物／設備／土地・耐用年数 | `config/kurashift_re_property_master.yaml` の `book:`（**税務反映済み**／法人償却明細は未OCR） |
| 現預金 | MQ軽量BS `cash`（名義別） |
| 資本金等 | `config/re_business_pl_overrides.yaml` |
| **法人・確定決算／事業計画** | `kurashift_re_statements` / `kurashift_re_annual_plans`（Kneesbee・MyKomon・**Zaimより優先**） |
| **総勘定元帳** | `kurashift_re_gl_lines`（科目一覧は re-pl パネル） |

### 税務ソース（2026-08-24 反映）

| 物件 | ソース | 反映内容 |
|---|---|---|
| GrandoleⅡ | 令和7年分収支内訳書（不動産） | 建物取得 32,119,650／定額0.08412／年償却 2,698,051。土地=本体−建物 |
| キャラメル | 同上 | 建物取得 21,090,413／定額0.05319（≈19年）。年償却は通年換算 |
| GrandoleⅠ | 第1期BS提出用サマリー（knees bee） | 建物 30,956,040／土地 37,073,217。申告書一式は画像PDFのため償却明細は未OCR |

### 法人正本（2026-08-30 · R8＋事業計画）

| 項目 | 内容 |
|---|---|
| 面談 | Notion 2026-08-28「2期目決算報告・事業計画書レビュー」 |
| 取込 | `scripts/jarvis_kurashift_re_statement_ingest.py` ← OneDrive `2期終了_202608/` |
| MyKomon DL | `tax_docs_tools/mykomon_fetch_business_plan.py` |
| UI | `/mq?view=re-pl` · 主体「法人」で statement 優先。「合算」は個人Zaim＋法人statement列 |
| ゲート | `01_突合ゲート.md`（税引前 ▲1,190,714 一致） |

---

## 計算（Excel準拠）

- 税前 = 収入 − 経費（償却除く） − 減価償却 − 支払利息  
- 税金 = max(0, 税前 × 20%)（初回固定）※法人 statement がある年は税額を statement 優先  
- CF = 税後 + 償却 + 税金 − 税金支払 − 元金返済  
- 自己資本比率 = 純資産 / 資産合計  
- 流動比率 = 流動資産 / 流動負債  
- 債務償還年数 = 固定負債 / 年CF  
- ROI = 年CF / 純資産  

---

## コード

- `lib/reBusinessPlTypes.ts` / `reBusinessPlMath.ts` / `reBusinessPlCompose.ts` / `reKneesbeeOverlay.ts`
- `components/ReBusinessPlPanel.tsx`
- レーン: `MqLaneNav` の `view=re-pl`
- migration: `apps/jarvis-dashboard/supabase/migrations/20260830_kurashift_re_statements_plans_gl.sql`

---

## 未実装（意図的）

- Excel購入ケースのシミュレーション取込  
- 法人申告書（画像PDF）の OCR による償却明細自動取得  
- 家計BSへの自動加算  
- 物件別Zaim紐づけの完全自動化（摘要ヒント＋未配分列）  
- 元帳行の deals 案件紐づけ UI（科目集計までは実装）  
- 7/1 サブリース契約変更（評価表示のみ・契約作業は別）  

---

## 相談フレーム

1. 事業PL税後利益と資金繰りCFの差＝元本・償却の見え方  
2. MQのGとゼミ税前利益＝ものさしの差  
3. 家計BSの不動産資産と事業BS固定資産の境界  
