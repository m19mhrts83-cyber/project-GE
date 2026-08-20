/** 期末手入力・処置シミュレーション → 列上書きマップ */

import type { CashflowColumnKey } from "./mqCashflowColumns";

export const ADJUSTMENT_FIELD_KEYS: CashflowColumnKey[] = [
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
  "interest_yearend",
  "tax_payment",
  "action_inflow",
];

export type CashflowAdjustmentRow = {
  id?: string;
  business_line: string;
  entity: string;
  period_month: string;
  field_key: string;
  amount_man: number | string;
  source?: string;
  note?: string | null;
};

export type CashflowActionKind = "officer" | "borrow_st" | "borrow_lt";

export type CashflowActionRow = {
  id?: string;
  business_line: string;
  entity: string;
  period_month: string;
  action_kind: CashflowActionKind;
  amount_man: number | string;
  label?: string | null;
  is_active?: boolean | null;
  sort_order?: number | null;
};

export function isAdjustmentFieldKey(raw: string): raw is CashflowColumnKey {
  return (ADJUSTMENT_FIELD_KEYS as string[]).includes(raw);
}

function monthKey(raw: string): string {
  return String(raw).slice(0, 7);
}

function num(v: number | string | null | undefined): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function entityOk(
  rowEntity: string,
  filter: string
): boolean {
  if (filter === "combined") {
    return rowEntity === "personal" || rowEntity === "corporate";
  }
  return rowEntity === filter;
}

export function adjustmentsToByMonth(
  rows: CashflowAdjustmentRow[],
  businessLine: string,
  entity: string
): Record<string, Partial<Record<CashflowColumnKey, number>>> {
  const out: Record<string, Partial<Record<CashflowColumnKey, number>>> = {};
  for (const r of rows) {
    if (r.business_line !== businessLine) continue;
    if (!entityOk(r.entity, entity)) continue;
    if (!isAdjustmentFieldKey(r.field_key)) continue;
    const mo = monthKey(r.period_month);
    const prev = out[mo] ?? {};
    const key = r.field_key;
    prev[key] = (prev[key] ?? 0) + num(r.amount_man);
    out[mo] = prev;
  }
  return out;
}

/** 有効な処置を action_inflow 列へ合算 */
export function mergeActionsIntoAdjustments(
  base: Record<string, Partial<Record<CashflowColumnKey, number>>>,
  actions: CashflowActionRow[],
  businessLine: string,
  entity: string
): Record<string, Partial<Record<CashflowColumnKey, number>>> {
  const out: Record<string, Partial<Record<CashflowColumnKey, number>>> = {};
  for (const [mo, cols] of Object.entries(base)) {
    out[mo] = { ...cols };
  }
  for (const a of actions) {
    if (a.business_line !== businessLine) continue;
    if (!entityOk(a.entity, entity)) continue;
    if (a.is_active === false) continue;
    const amt = num(a.amount_man);
    if (amt <= 0) continue;
    const mo = monthKey(a.period_month);
    const prev = out[mo] ?? {};
    prev.action_inflow = (prev.action_inflow ?? 0) + amt;
    out[mo] = prev;
  }
  return out;
}

export function actionKindLabel(kind: CashflowActionKind): string {
  if (kind === "officer") return "個人借入";
  if (kind === "borrow_st") return "短期借入";
  return "長期借入";
}

export function pickYearendAdjustment(
  rows: CashflowAdjustmentRow[],
  args: {
    businessLine: string;
    entity: string;
    year: number;
    field: "interest_yearend" | "tax_payment";
  }
): CashflowAdjustmentRow | null {
  const prefix = `${args.year}-`;
  const hits = rows.filter(
    (r) =>
      r.business_line === args.businessLine &&
      r.entity === args.entity &&
      String(r.period_month).startsWith(prefix) &&
      r.field_key === args.field
  );
  hits.sort((a, b) => String(a.period_month).localeCompare(String(b.period_month)));
  return hits[hits.length - 1] ?? null;
}
