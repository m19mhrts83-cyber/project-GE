import type { FinanceTxnLite } from "./mqZaimMap";
import type { EntityFilter } from "./mqAggregate";
import type { CashflowColumnKey } from "./mqCashflowColumns";
import { CASHFLOW_COLUMN_LABELS } from "./mqCashflowColumns";
import type { CashflowClassifyRuleRow, TxnOverrideRow } from "./mqCashflowClassify";
import {
  buildOverrideMap,
  detectFireInsurance,
  resolveCashflowColumn,
  type ClassifyReason,
} from "./mqCashflowClassify";

export type CashflowLineItemSource =
  | "txn"
  | "loan_tracker"
  | "adjustment"
  | "action"
  | "residual"
  | "computed";

export type CashflowLineItem = {
  id: string;
  source: CashflowLineItemSource;
  txnId?: number;
  txnDate: string | null;
  category: string | null;
  subcategory: string | null;
  place: string | null;
  entity: string | null;
  amountMan: number;
  columnKey: CashflowColumnKey;
  classifyReason: ClassifyReason | "manual" | "residual";
  classifyDetail?: string;
};

/** 内訳行の表示タグ（火災保険など） */
export function lineItemDisplayTag(item: CashflowLineItem): string | null {
  const blob = [item.category, item.subcategory, item.place]
    .filter(Boolean)
    .join(" ");
  if (detectFireInsurance(blob)) return "火災保険";
  return null;
}

export type LoanTrackerLite = {
  id: string;
  name: string | null;
  lender: string | null;
  monthly_payment_jpy: number | string | null;
};

function yenToManRounded(yen: number): number {
  return Math.round((Number(yen) || 0) / 10_000);
}

export function txnPlace(txn: FinanceTxnLite): string {
  const d = (txn.description || "").trim();
  if (d) return d;
  const to = (txn.to_account || "").trim();
  if (to) return to;
  const from = (txn.from_account || "").trim();
  if (from) return from;
  const memo = (txn.memo || "").trim();
  if (memo) return memo;
  return "（摘要なし）";
}

function monthKeyFromTxnDate(txn_date: string | null): string | null {
  if (!txn_date || txn_date.length < 7) return null;
  return String(txn_date).slice(0, 7);
}

function signedAmountMan(column: CashflowColumnKey, yen: number): number {
  const man = yenToManRounded(yen);
  const inflow: CashflowColumnKey[] = [
    "sales",
    "borrow_lt",
    "borrow_st",
    "borrow_officer",
    "action_inflow",
  ];
  if (inflow.includes(column)) return man;
  return -man;
}

export function buildCashflowLineItems(args: {
  year: number;
  entity: EntityFilter;
  businessLine: string;
  txns: FinanceTxnLite[];
  txnOverrides?: TxnOverrideRow[];
  classifyRules?: CashflowClassifyRuleRow[];
  loanTracker?: LoanTrackerLite[];
  loanMonthlyPaymentMan?: number | null;
}): CashflowLineItem[] {
  const {
    year,
    entity,
    businessLine,
    txns,
    txnOverrides = [],
    classifyRules = [],
    loanTracker = [],
    loanMonthlyPaymentMan = null,
  } = args;

  const overrides = buildOverrideMap(txnOverrides, businessLine);
  const items: CashflowLineItem[] = [];

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

    const yen = inc > 0 ? inc : exp;
    const txnId = t.id != null ? Number(t.id) : undefined;

    items.push({
      id: txnId != null ? `txn-${txnId}` : `txn-${mo}-${items.length}`,
      source: "txn",
      txnId,
      txnDate: t.txn_date,
      category: t.category,
      subcategory: t.subcategory,
      place: txnPlace(t),
      entity: t.entity,
      amountMan: signedAmountMan(resolved.column, yen),
      columnKey: resolved.column,
      classifyReason: resolved.reason,
      classifyDetail: resolved.detail,
    });
  }

  if (loanMonthlyPaymentMan != null && loanMonthlyPaymentMan > 0) {
    for (let m = 1; m <= 12; m++) {
      const mo = `${year}-${String(m).padStart(2, "0")}`;
      if (loanTracker.length > 0) {
        for (const loan of loanTracker) {
          const pay = yenToManRounded(Number(loan.monthly_payment_jpy) || 0);
          if (pay <= 0) continue;
          items.push({
            id: `loan-${loan.id}-${mo}`,
            source: "loan_tracker",
            txnDate: `${mo}-01`,
            category: "ローン",
            subcategory: "返済",
            place: [loan.lender, loan.name].filter(Boolean).join(" · ") || "借入",
            entity: null,
            amountMan: -pay,
            columnKey: "loan_repayment",
            classifyReason: "manual",
            classifyDetail: "loan tracker 月額",
          });
        }
      } else {
        items.push({
          id: `loan-flat-${mo}`,
          source: "loan_tracker",
          txnDate: `${mo}-01`,
          category: "ローン",
          subcategory: "返済",
          place: "借入残高トラッカー合算",
          entity: null,
          amountMan: -loanMonthlyPaymentMan,
          columnKey: "loan_repayment",
          classifyReason: "manual",
          classifyDetail: "loan tracker 合算月額",
        });
      }
    }
  }

  return items;
}

export function lineItemsForCell(
  items: CashflowLineItem[],
  month: string,
  columnKey: CashflowColumnKey
): CashflowLineItem[] {
  return items.filter((it) => {
    const mo = monthKeyFromTxnDate(it.txnDate);
    return mo === month && it.columnKey === columnKey;
  });
}

export function buildCellDetailResponse(args: {
  month: string;
  columnKey: CashflowColumnKey;
  cellTotalMan: number | null;
  items: CashflowLineItem[];
}): {
  header: {
    month: string;
    columnKey: CashflowColumnKey;
    columnLabel: string;
    totalMan: number | null;
    txnCount: number;
    hasResidual: boolean;
  };
  items: CashflowLineItem[];
  reclassifiable: boolean;
} {
  const { month, columnKey, cellTotalMan, items } = args;
  const matched = lineItemsForCell(items, month, columnKey);
  const sumItems = matched.reduce((s, it) => s + it.amountMan, 0);
  const out = [...matched];

  let hasResidual = false;
  if (cellTotalMan != null && matched.length > 0) {
    const inflow =
      columnKey === "sales" ||
      columnKey.startsWith("borrow_") ||
      columnKey === "action_inflow";
    const displayTotal = inflow
      ? Math.abs(cellTotalMan)
      : -Math.abs(cellTotalMan);
    const residual = Math.round((displayTotal - sumItems) * 10) / 10;
    if (Math.abs(residual) >= 1) {
      hasResidual = true;
      out.push({
        id: `residual-${month}-${columnKey}`,
        source: "residual",
        txnDate: null,
        category: null,
        subcategory: null,
        place: "端数調整（facts/Zaim との差）",
        entity: null,
        amountMan: residual,
        columnKey,
        classifyReason: "residual",
        classifyDetail: "表セルと明細合計の差",
      });
    }
  }

  const reclassifiable = matched.some(
    (it) => it.source === "txn" && it.txnId != null
  );

  return {
    header: {
      month,
      columnKey,
      columnLabel: CASHFLOW_COLUMN_LABELS[columnKey],
      totalMan: cellTotalMan,
      txnCount: matched.filter((it) => it.source === "txn").length,
      hasResidual,
    },
    items: out,
    reclassifiable,
  };
}

/** 内訳行が列再分類可能か（txn 由来のみ） */
export function isLineItemReclassifiable(item: CashflowLineItem): boolean {
  return item.source === "txn" && item.txnId != null;
}

export function rowFieldToColumn(rowField: string): CashflowColumnKey | null {
  const map: Record<string, CashflowColumnKey> = {
    salesMan: "sales",
    borrowLtMan: "borrow_lt",
    borrowStMan: "borrow_st",
    borrowOfficerMan: "borrow_officer",
    repairMan: "repair",
    advertisingMan: "advertising",
    expenseMan: "expense",
    managementMan: "management",
    acquisitionMan: "acquisition",
    taxAccountantMan: "tax_accountant",
    loanRepaymentMan: "loan_repayment",
    annualTaxMan: "annual_tax",
    interestYearendMan: "interest_yearend",
    taxPaymentMan: "tax_payment",
    actionInflowMan: "action_inflow",
  };
  return map[rowField] ?? null;
}

export const CLICKABLE_ROW_FIELDS = new Set([
  "salesMan",
  "borrowLtMan",
  "borrowStMan",
  "borrowOfficerMan",
  "repairMan",
  "advertisingMan",
  "expenseMan",
  "managementMan",
  "acquisitionMan",
  "taxAccountantMan",
  "loanRepaymentMan",
  "annualTaxMan",
  "interestYearendMan",
  "taxPaymentMan",
  "actionInflowMan",
]);
