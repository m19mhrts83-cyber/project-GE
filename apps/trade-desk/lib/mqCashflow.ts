import type { FinanceTxnLite, MqAccountMapRow } from "./mqZaimMap";
import type { EntityFilter, LineFilter } from "./mqAggregate";
import { formatRatio } from "./mqEquations";
import type { CashflowClassifyRuleRow, TxnOverrideRow } from "./mqCashflowClassify";
import {
  buildOverrideMap,
  resolveCashflowColumn,
} from "./mqCashflowClassify";
import type { CashflowColumnKey } from "./mqCashflowColumns";
import { columnToRowField } from "./mqCashflowColumns";

export type { CashflowBucketKey } from "./mqCashflowColumns";

export type MqCashflowMonthRow = {
  month: string; // YYYY-MM
  cashBeginMan: number | null;
  salesMan: number | null;
  borrowLtMan: number | null;
  borrowStMan: number | null;
  borrowOfficerMan: number | null;
  loanRepaymentMan: number | null;
  repairMan: number | null;
  advertisingMan: number | null;
  expenseMan: number | null;
  managementMan: number | null;
  acquisitionMan: number | null;
  taxAccountantMan: number | null;
  annualTaxMan: number | null;
  interestYearendMan: number | null;
  taxPaymentMan: number | null;
  actionInflowMan: number | null;
  cashEndMan: number | null;
  netCashFlowMan: number | null;
  isNegative: boolean;
  yearendCarryMan: number | null;
  repaymentRatio: number | null;
};

function yenToManRounded(yen: number): number {
  return Math.round((Number(yen) || 0) / 10_000);
}

function safeNum(n: number | null | undefined): number | null {
  if (n == null || !Number.isFinite(Number(n))) return null;
  return Number(n);
}

function monthKeyFromTxnDate(txn_date: string | null): string | null {
  if (!txn_date || txn_date.length < 7) return null;
  return String(txn_date).slice(0, 7);
}

type ColumnSums = Partial<Record<CashflowColumnKey, number>>;

function emptyColumnSums(): ColumnSums {
  return {};
}

function addToColumn(sums: ColumnSums, col: CashflowColumnKey, man: number) {
  sums[col] = (sums[col] ?? 0) + man;
}

export function buildMqCashflowMonthRows(args: {
  year: number;
  months: string[];
  line: LineFilter;
  entity: EntityFilter;
  cashBeginMan: number | null;
  loanMonthlyPaymentMan: number | null;
  factsCashByMonth?: Record<
    string,
    {
      cashInMan: number | null;
      cashOutMan: number | null;
      cashEndMan: number | null;
    }
  >;
  txns: FinanceTxnLite[];
  maps: MqAccountMapRow[];
  businessLine?: string;
  txnOverrides?: TxnOverrideRow[];
  classifyRules?: CashflowClassifyRuleRow[];
  /** 月別・列別の手動調整（万円） */
  adjustmentsByMonth?: Record<string, Partial<Record<CashflowColumnKey, number>>>;
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
    businessLine = line === "ai" ? "ai" : "realestate",
    txnOverrides = [],
    classifyRules = [],
    adjustmentsByMonth = {},
  } = args;

  const overrides = buildOverrideMap(txnOverrides, businessLine);

  // maps は呼び出し互換のため受け取る（列集計はホワイトリスト分類のみ）
  void maps;
  void line;

  const columnSumsByMonth = new Map<string, ColumnSums>();

  for (const t of txns) {
    const mo = monthKeyFromTxnDate(t.txn_date);
    if (!mo || !mo.startsWith(String(year))) continue;
    if (entity !== "combined" && t.entity !== entity) continue;

    const inc = Number(t.income_jpy) || 0;
    const exp = Number(t.expense_jpy) || 0;
    if (inc <= 0 && exp <= 0) continue;

    const resolved = resolveCashflowColumn(t, {
      businessLine,
      overrides,
      rules: classifyRules,
    });
    if (resolved.column == null || resolved.reason === "excluded") continue;

    const amountMan =
      inc > 0 ? yenToManRounded(inc) : yenToManRounded(exp);

    const sums = columnSumsByMonth.get(mo) ?? emptyColumnSums();
    addToColumn(sums, resolved.column, amountMan);
    columnSumsByMonth.set(mo, sums);
  }

  let cashCursor = cashBeginMan;
  const out: MqCashflowMonthRow[] = [];

  for (let i = 0; i < months.length; i++) {
    const mo = months[i]!;
    const cashFacts = factsCashByMonth?.[mo] ?? null;
    const adj = adjustmentsByMonth[mo] ?? {};

    const col = columnSumsByMonth.get(mo) ?? emptyColumnSums();

    const pick = (key: CashflowColumnKey): number | null => {
      const fromTxn = col[key];
      const fromAdj = adj[key];
      if (fromTxn == null && fromAdj == null) return null;
      return (fromTxn ?? 0) + (fromAdj ?? 0);
    };

    let salesMan = pick("sales");
    // 売上は事業ホワイトリスト分類のみ（全収入 cash_in へのフォールバックはしない）

    let loanMan =
      line === "ai"
        ? null
        : pick("loan_repayment") ??
          (loanMonthlyPaymentMan == null ? null : loanMonthlyPaymentMan);

    const repairMan = pick("repair");
    const advertisingMan = pick("advertising");
    const expenseMan = pick("expense");
    const managementMan = pick("management");
    const acquisitionMan = pick("acquisition");
    const taxAccountantMan = pick("tax_accountant");
    const annualTaxMan = pick("annual_tax");
    const borrowLtMan = pick("borrow_lt");
    const borrowStMan = pick("borrow_st");
    const borrowOfficerMan = pick("borrow_officer");
    const interestYearendMan = pick("interest_yearend");
    const taxPaymentMan = pick("tax_payment");
    const actionInflowMan = pick("action_inflow");

    const outflowParts = [
      repairMan,
      advertisingMan,
      expenseMan,
      managementMan,
      acquisitionMan,
      taxAccountantMan,
      annualTaxMan,
      loanMan,
      interestYearendMan,
      taxPaymentMan,
    ];
    const inflowParts = [
      salesMan,
      borrowLtMan,
      borrowStMan,
      borrowOfficerMan,
      actionInflowMan,
    ];

    const sumParts = (parts: (number | null)[]): number | null => {
      if (parts.every((p) => p == null)) return null;
      return parts.reduce<number>((s, p) => s + (p ?? 0), 0);
    };

    const totalIn = sumParts(inflowParts);
    const totalOut = sumParts(outflowParts);
    let netCashFlowMan: number | null = null;
    if (totalIn != null || totalOut != null) {
      netCashFlowMan = (totalIn ?? 0) - (totalOut ?? 0);
    }
    // 事業列が空のときでも、ライフプラン込みの cash_in/out では埋めない

    const monthBegin =
      i === 0 ? cashBeginMan : (out[i - 1]?.cashEndMan ?? null);

    let cashEndMan: number | null = cashFacts?.cashEndMan ?? null;
    if (cashEndMan == null && monthBegin != null) {
      cashCursor = monthBegin + (netCashFlowMan ?? 0);
      cashEndMan = cashCursor;
    } else if (cashEndMan != null) {
      cashCursor = cashEndMan;
    }

    const isNegative = cashEndMan != null && cashEndMan < 0;
    const isDecember = mo.endsWith("-12");
    const yearendCarryMan =
      isDecember && cashEndMan != null ? cashEndMan : null;

    const repaymentRatio =
      loanMan != null && salesMan != null && salesMan > 0
        ? loanMan / salesMan
        : null;

    out.push({
      month: mo,
      cashBeginMan: monthBegin,
      salesMan: safeNum(salesMan),
      borrowLtMan: safeNum(borrowLtMan),
      borrowStMan: safeNum(borrowStMan),
      borrowOfficerMan: safeNum(borrowOfficerMan),
      loanRepaymentMan: loanMan,
      repairMan: safeNum(repairMan),
      advertisingMan: safeNum(advertisingMan),
      expenseMan: safeNum(expenseMan),
      managementMan: safeNum(managementMan),
      acquisitionMan: safeNum(acquisitionMan),
      taxAccountantMan: safeNum(taxAccountantMan),
      annualTaxMan: safeNum(annualTaxMan),
      interestYearendMan: safeNum(interestYearendMan),
      taxPaymentMan: safeNum(taxPaymentMan),
      actionInflowMan: safeNum(actionInflowMan),
      cashEndMan,
      netCashFlowMan,
      isNegative,
      yearendCarryMan,
      repaymentRatio,
    });
  }

  return out;
}

export function repaymentRatioText(r: number | null): string {
  if (r == null || !Number.isFinite(r)) return "—";
  return formatRatio(r);
}

export function decemberCashEnd(rows: MqCashflowMonthRow[]): number | null {
  const dec = rows.find((r) => r.month.endsWith("-12"));
  return dec?.cashEndMan ?? dec?.yearendCarryMan ?? null;
}

export { columnToRowField };
