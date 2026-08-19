# 家計B/S — 不動産フローの準拠

家計B/S（`/household-bs`）の不動産の収入・支出を、何を正にしてどう処理するかを固定する。  
分類の機械正本は `config/household_kiyosaki_bs.yaml` の `realestate_flow` / `expense_flow`。  
申告数字の機械正本は `config/kurashift_tax_year_metrics.yaml`（提出PDFから抽出 → `kurashift_tax_year_metrics`）。

## 準拠（優先順）

| 見たいもの | 正 | 使わない |
|---|---|---|
| **家賃収入（申告済みの年）** | 確定申告。個人＝収支内訳書の**収入金額**（`payload.re_revenue_jpy`）。法人があれば申告の**売上**（5月期） | 財務19.1、MQ PQ、いまの内容確認を合計に足すこと |
| **家賃収入（未申告の年）** | 内容確認＝`property_units` の入居中号室。`家賃 + 管理費` × **その年の所有月数** | 財務19.1、MQ PQ |
| **管理費（支出）** | 未申告年だけ内容確認の管理費を戻す。申告済み年は収入を申告のまま使う（経費は申告側でコントロール済み） | 財務年次の 19F 一括 |
| **その他不動産収入** | 財務年次の `19.2` 売却・`19.4` 事業収入・`19.6` 保険金 | `19.1` 家賃 |
| **家計の生活支出** | 財務年次の家計科目 | `合計` 行、`19*` / 賃貸 / マンション経営 |
| **MQ PQ・VQ+F** | `/mq` と家計B/Sの参考カード | 家計4象限の合計 |

## 申告後の差し替え（毎年）

1. 提出PDFを OneDrive `50_税金,確定申告/{年}年度/`（個人）または `knees bee 税理士法人/3.決算/`（法人）へ置く
2. `config/kurashift_tax_year_metrics.yaml` の `re_revenue_jpy`（個人）／`revenue_jpy`（法人）を更新
3. `scripts/jarvis_kurashift_tax.py --import-metrics-catalog`
4. 家計B/Sはその年を **live compose**（古いスナップは申告行が無いと使わない）

収入は申告した実績のまま載せる。経費を家計B/Sで作り直さない。

## 所有月数（未申告年の内容確認）

- 過去年: その年の 1–12 月のうち、取得日以降
- 当年: **今日の月まで**（2026年8月なら8ヶ月。年換算しない）
- 取得日が月の16日以降なら **翌月から**（キャラメル 2025-12-26 → 2026-01〜）

## 管理費の補正（未申告年のみ）

財務の家賃入金（19.1）は管理費を差し引いた NET。未申告年の家計B/Sでは:

1. 収入 = 内容確認のグロス（家賃+管理費）
2. 支出 = 同じ内容確認の管理費

申告済み年は、収支内訳の収入金額をそのまま使う。

## 関連

- 号室正: ③-C `/realestate/properties`、`property_units`
- 申告KPI: `config/kurashift_tax_year_metrics.yaml`
- 合成: `apps/trade-desk/lib/householdReFiled.ts` / `householdReFlow.ts` → `householdBsCompose.ts`
