/** 資金繰り表の列キー（UI・DB・分類ルール共通） */

export type CashflowColumnKey =
  | "sales"
  | "borrow_lt"
  | "borrow_st"
  | "borrow_officer"
  | "repair"
  | "advertising"
  | "expense"
  | "management"
  | "acquisition"
  | "tax_accountant"
  | "loan_repayment"
  | "annual_tax"
  | "interest_yearend"
  | "tax_payment"
  | "action_inflow";

/** 便宜分類バケット → 列キー */
export type CashflowBucketKey =
  | "repair"
  | "advertising"
  | "expense"
  | "management"
  | "acquisition"
  | "taxAccountant"
  | "annualTax";

export const CASHFLOW_COLUMN_LABELS: Record<CashflowColumnKey, string> = {
  sales: "売上",
  borrow_lt: "長期借入",
  borrow_st: "短期借入",
  borrow_officer: "個人借入",
  repair: "修繕",
  advertising: "広告",
  expense: "経費",
  management: "管理費",
  acquisition: "取得時",
  tax_accountant: "税理士",
  loan_repayment: "返済",
  annual_tax: "年払・税",
  interest_yearend: "利息（期末）",
  tax_payment: "税金支払",
  action_inflow: "処置（計画）",
};

export const BUCKET_TO_COLUMN: Record<CashflowBucketKey, CashflowColumnKey> = {
  repair: "repair",
  advertising: "advertising",
  expense: "expense",
  management: "management",
  acquisition: "acquisition",
  taxAccountant: "tax_accountant",
  annualTax: "annual_tax",
};

/** 再分類 UI の選択肢（収入→出金） */
export const RECLASSIFY_COLUMN_OPTIONS: CashflowColumnKey[] = [
  "sales",
  "borrow_lt",
  "borrow_st",
  "borrow_officer",
  "repair",
  "advertising",
  "expense",
  "management",
  "acquisition",
  "tax_accountant",
  "loan_repayment",
  "annual_tax",
];

export function columnToRowField(
  col: CashflowColumnKey
): keyof import("./mqCashflow").MqCashflowMonthRow | null {
  const map: Partial<
    Record<CashflowColumnKey, keyof import("./mqCashflow").MqCashflowMonthRow>
  > = {
    sales: "salesMan",
    borrow_lt: "borrowLtMan",
    borrow_st: "borrowStMan",
    borrow_officer: "borrowOfficerMan",
    repair: "repairMan",
    advertising: "advertisingMan",
    expense: "expenseMan",
    management: "managementMan",
    acquisition: "acquisitionMan",
    tax_accountant: "taxAccountantMan",
    loan_repayment: "loanRepaymentMan",
    annual_tax: "annualTaxMan",
    interest_yearend: "interestYearendMan",
    tax_payment: "taxPaymentMan",
    action_inflow: "actionInflowMan",
  };
  return map[col] ?? null;
}
