import type { FinanceTxnLite, MqAccountMapRow } from "./mqZaimMap";
import type { EntityFilter, LineFilter } from "./mqAggregate";
import { aggregateZaimToMq } from "./mqZaimMap";
import { formatRatio } from "./mqEquations";

export type CashflowBucketKey =
  | "repair"
  | "advertising"
  | "expense"
  | "management"
  | "acquisition"
  | "taxAccountant"
  | "annualTax";

export type MqCashflowMonthRow = {
  month: string; // YYYY-MM
  salesMan: number | null; // 売上（cash_in）
  loanRepaymentMan: number | null; // ローン返済（別行）

  // 経費側（ローン除く）を便宜分類して列に出す
  repairMan: number | null;
  advertisingMan: number | null;
  expenseMan: number | null;
  managementMan: number | null;
  acquisitionMan: number | null;
  taxAccountantMan: number | null;
  annualTaxMan: number | null;

  // 现金
  cashEndMan: number | null; // 期末現金
  netCashFlowMan: number | null; // 差引キャッシュ増減（売上 - 出金）

  // 参考指標（実装は“別計算”せず、月次の数値から読める前提）
  repaymentRatio: number | null; // ローン返済 / 売上
};

function yenToManRounded(yen: number): number {
  return Math.round((Number(yen) || 0) / 10_000);
}

function safeNum(n: number | null | undefined): number | null {
  if (n == null || !Number.isFinite(Number(n))) return null;
  return Number(n);
}

function toLower(s: string | null | undefined): string {
  return (s ?? "").toLowerCase();
}

function matchesAny(hay: string, needles: readonly string[]): boolean {
  const h = toLower(hay);
  return needles.some((n) => h.includes(n.toLowerCase()));
}

type TxnClassification = {
  isLoan: boolean;
  bucket: CashflowBucketKey | null;
};

function classifyExpenseTxn(
  txn: FinanceTxnLite
): TxnClassification {
  const cat = toLower(txn.category);
  const sub = toLower(txn.subcategory);
  const blob = `${cat} ${sub}`;

  // 1) ローン返済（除外）
  const isLoan = matchesAny(blob, [
    "ローン",
    "返済",
    "借入返済",
    "支払（ローン",
    "融資返済",
  ]);
  if (isLoan) return { isLoan: true, bucket: null };

  // 2) 税理士（法人の定常報酬 / 購入時の税理士費用）
  if (matchesAny(blob, ["税理士"])) {
    // “報酬/顧問”寄りなら定常の税理士報酬へ寄せる
    if (matchesAny(blob, ["報酬", "顧問", "顧問料"])) {
      return { isLoan: false, bucket: "taxAccountant" };
    }
    return { isLoan: false, bucket: "acquisition" };
  }

  // 3) 火災保険・ローン手数料などの購入時費用
  if (matchesAny(blob, ["火災保険", "保険料"])) {
    return { isLoan: false, bucket: "acquisition" };
  }
  if (matchesAny(blob, ["手数料", "保証料", "登記", "印紙", "融資"])) {
    return { isLoan: false, bucket: "acquisition" };
  }

  // 4) 年払い・税金などの大口出金
  if (matchesAny(blob, ["固定資産税", "都市計画税", "税金", "租税"])) {
    return { isLoan: false, bucket: "annualTax" };
  }

  // 5) 管理費（共用部）
  if (
    matchesAny(blob, [
      "管理費",
      "共益",
      "水道",
      "電気",
      "インターネット",
      "ネット",
      "通信",
    ])
  ) {
    return { isLoan: false, bucket: "management" };
  }

  // 6) 修繕（原状回復/リフォーム）
  if (
    matchesAny(blob, [
      "修繕",
      "リフォーム",
      "原状回復",
      "改修",
      "クロス",
      "設備交換",
      "工事",
    ])
  ) {
    return { isLoan: false, bucket: "repair" };
  }

  // 7) 広告
  if (matchesAny(blob, ["広告", "宣伝", "募集", "掲載"])) {
    return { isLoan: false, bucket: "advertising" };
  }

  // 8) 残りは “経費（ステージング/空室対策/その他）”
  return { isLoan: false, bucket: "expense" };
}

function monthKeyFromTxnDate(txn_date: string | null): string | null {
  if (!txn_date || txn_date.length < 7) return null;
  return String(txn_date).slice(0, 7);
}

export function buildMqCashflowMonthRows(args: {
  year: number;
  months: string[]; // YYYY-MM
  line: LineFilter;
  entity: EntityFilter;
  cashBeginMan: number | null;
  loanMonthlyPaymentMan: number | null;
  factsCashByMonth?: Record<
    string,
    { cashInMan: number | null; cashOutMan: number | null; cashEndMan: number | null }
  >;
  txns: FinanceTxnLite[];
  maps: MqAccountMapRow[];
}): MqCashflowMonthRow[] {
  const {
    year,
    months,
    line,
    entity,
    cashBeginMan,
    loanMonthlyPaymentMan,
    factsCashByMonth,
    txns,
    maps,
  } = args;

  const agg = aggregateZaimToMq(txns, maps, { year });
  const buckets = agg.buckets;

  function includeBucket(business_line: string, ent: string): boolean {
    const lineOk = line === "all" ? true : business_line === line;
    const entityOk =
      entity === "combined"
        ? ent === "personal" || ent === "corporate"
        : ent === entity;
    return lineOk && entityOk;
  }

  const cashFromTxns = new Map<
    string,
    { cashInMan: number; cashOutMan: number }
  >();
  for (const b of buckets) {
    if (!includeBucket(b.business_line, b.entity)) continue;
    const mo = b.period_month.slice(0, 7);
    const prev = cashFromTxns.get(mo) ?? { cashInMan: 0, cashOutMan: 0 };
    cashFromTxns.set(mo, {
      cashInMan: prev.cashInMan + yenToManRounded(b.cash_in),
      cashOutMan: prev.cashOutMan + yenToManRounded(b.cash_out),
    });
  }

  const rawBucketsByMonth = new Map<
    string,
    Record<CashflowBucketKey, number>
  >();

  const emptyRaw: Record<CashflowBucketKey, number> = {
    repair: 0,
    advertising: 0,
    expense: 0,
    management: 0,
    acquisition: 0,
    taxAccountant: 0,
    annualTax: 0,
  };

  for (const t of txns) {
    const mo = monthKeyFromTxnDate(t.txn_date);
    if (!mo) continue;
    if (!mo.startsWith(String(year))) continue;
    if (!t.expense_jpy || Number(t.expense_jpy) <= 0) continue;

    if (entity !== "combined" && t.entity !== entity) continue;

    // line によって txns を絞るのは厳密には難しいので、分類＆スケールで整合を取る
    const cls = classifyExpenseTxn(t);
    if (cls.isLoan || !cls.bucket) continue;

    const prev = rawBucketsByMonth.get(mo) ?? { ...emptyRaw };
    const expMan = yenToManRounded(Number(t.expense_jpy));
    prev[cls.bucket] += expMan;
    rawBucketsByMonth.set(mo, prev);
  }

  // cash_end は facts があればそれを優先。なければ cashFromTxns の累積で作る
  let cashCursor = cashBeginMan;
  const out: MqCashflowMonthRow[] = [];

  for (const mo of months) {
    const cashTx = cashFromTxns.get(mo) ?? null;
    const cashFacts = factsCashByMonth?.[mo] ?? null;

    const cashInMan = cashFacts?.cashInMan ?? (cashTx ? cashTx.cashInMan : null);
    const cashOutMan = cashFacts?.cashOutMan ?? (cashTx ? cashTx.cashOutMan : null);

    const loanMan =
      line === "ai" ? null : loanMonthlyPaymentMan == null ? null : loanMonthlyPaymentMan;

    const netCashFlowMan =
      cashInMan != null && cashOutMan != null ? cashInMan - cashOutMan : null;

    // cash_end
    let cashEndMan: number | null = cashFacts?.cashEndMan ?? null;
    if (cashEndMan == null && cashCursor != null && netCashFlowMan != null) {
      cashCursor += netCashFlowMan;
      cashEndMan = cashCursor;
    }

    // 経費側（ローン除く）
    const expenseTotalMan =
      cashOutMan != null && loanMan != null ? cashOutMan - loanMan : null;
    const safeExpenseTotalMan =
      expenseTotalMan != null && expenseTotalMan >= 0 ? expenseTotalMan : null;

    const raw = rawBucketsByMonth.get(mo) ?? { ...emptyRaw };
    const rawSum =
      raw.repair +
      raw.advertising +
      raw.expense +
      raw.management +
      raw.acquisition +
      raw.taxAccountant +
      raw.annualTax;

    let repairMan = safeNum(raw.repair);
    let advertisingMan = safeNum(raw.advertising);
    let expenseMan = safeNum(raw.expense);
    let managementMan = safeNum(raw.management);
    let acquisitionMan = safeNum(raw.acquisition);
    let taxAccountantMan = safeNum(raw.taxAccountant);
    let annualTaxMan = safeNum(raw.annualTax);

    if (
      safeExpenseTotalMan != null &&
      rawSum > 0
    ) {
      // 端数のズレを吸収するため、まず丸めた後に最後の列へ残差を入れる
      const scale = safeExpenseTotalMan / rawSum;
      const scaled = {
        repair: Math.round(raw.repair * scale),
        advertising: Math.round(raw.advertising * scale),
        expense: Math.round(raw.expense * scale),
        management: Math.round(raw.management * scale),
        acquisition: Math.round(raw.acquisition * scale),
        taxAccountant: Math.round(raw.taxAccountant * scale),
        annualTax: Math.round(raw.annualTax * scale),
      } as const;

      const sumScaled =
        scaled.repair +
        scaled.advertising +
        scaled.expense +
        scaled.management +
        scaled.acquisition +
        scaled.taxAccountant +
        scaled.annualTax;
      const residual = safeExpenseTotalMan - sumScaled;
      // residual を “経費” に寄せる（最後の調整列）
      const expenseFinal = scaled.expense + residual;

      repairMan = scaled.repair;
      advertisingMan = scaled.advertising;
      managementMan = scaled.management;
      acquisitionMan = scaled.acquisition;
      taxAccountantMan = scaled.taxAccountant;
      annualTaxMan = scaled.annualTax;
      expenseMan = expenseFinal;
    }

    // repayment ratio
    const repaymentRatio =
      loanMan != null && cashInMan != null && cashInMan > 0
        ? loanMan / cashInMan
        : null;

    out.push({
      month: mo,
      salesMan: cashInMan,
      loanRepaymentMan: loanMan,
      repairMan,
      advertisingMan,
      expenseMan,
      managementMan,
      acquisitionMan,
      taxAccountantMan,
      annualTaxMan,
      cashEndMan,
      netCashFlowMan,
      repaymentRatio,
    });
  }

  return out;
}

export function repaymentRatioText(r: number | null): string {
  if (r == null || !Number.isFinite(r)) return "—";
  return formatRatio(r);
}

