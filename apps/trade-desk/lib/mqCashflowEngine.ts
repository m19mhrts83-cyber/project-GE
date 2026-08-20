/**
 * 資金繰り Engine — 起点・翌年繰越・複数年期首
 */

import type { EntityFilter, LineFilter } from "./mqAggregate";
import type { FinanceTxnLite, MqAccountMapRow } from "./mqZaimMap";
import {
  buildMqCashflowMonthRows,
  decemberCashEnd,
  type MqCashflowMonthRow,
} from "./mqCashflow";
import type { CashflowClassifyRuleRow, TxnOverrideRow } from "./mqCashflowClassify";
import {
  adjustmentsToByMonth,
  mergeActionsIntoAdjustments,
  type CashflowActionRow,
  type CashflowAdjustmentRow,
} from "./mqCashflowManual";
import {
  type MqCashflowSettings,
  type MqCashflowSettingsRow,
  openingCashFromSettings,
  originYearOf,
  settingsForEntity,
} from "./mqCashflowSettings";

export type CashflowEngineContext = {
  businessLine: string;
  entity: EntityFilter;
  settingsRows: MqCashflowSettingsRow[];
  txnOverrides: TxnOverrideRow[];
  classifyRules: CashflowClassifyRuleRow[];
  loanMonthlyPaymentMan: number | null;
  txns: FinanceTxnLite[];
  maps: MqAccountMapRow[];
  adjustments?: CashflowAdjustmentRow[];
  actions?: CashflowActionRow[];
  factsCashByMonthByYear: Record<
    number,
    Record<
      string,
      {
        cashInMan: number | null;
        cashOutMan: number | null;
        cashEndMan: number | null;
      }
    >
  >;
  bsFallbackOpeningByYear?: Record<number, number | null>;
};

function monthsOfYear(year: number): string[] {
  return Array.from({ length: 12 }, (_, i) => {
    return `${year}-${String(i + 1).padStart(2, "0")}`;
  });
}


function openingForYear(
  ctx: CashflowEngineContext,
  year: number,
  priorDecCash: number | null
): number | null {
  const line = ctx.businessLine;
  const ent = ctx.entity as "personal" | "corporate";
  const settings = settingsForEntity(ctx.settingsRows, line, ent);
  const fromSettings = openingCashFromSettings(settings, year);
  if (fromSettings != null) return fromSettings;
  const origin = originYearOf(settings);
  if (origin != null && year > origin) {
    return priorDecCash ?? ctx.bsFallbackOpeningByYear?.[year] ?? null;
  }
  return ctx.bsFallbackOpeningByYear?.[year] ?? null;
}

/** 単年分を期首から構築 */
export function buildCashflowYear(
  ctx: CashflowEngineContext,
  year: number,
  openingCashMan: number | null
): MqCashflowMonthRow[] {
  const line: LineFilter =
    ctx.businessLine === "ai" ? "ai" : "realestate";

  const adj = mergeActionsIntoAdjustments(
    adjustmentsToByMonth(
      ctx.adjustments ?? [],
      ctx.businessLine,
      ctx.entity
    ),
    ctx.actions ?? [],
    ctx.businessLine,
    ctx.entity
  );

  return buildMqCashflowMonthRows({
    year,
    months: monthsOfYear(year),
    line,
    entity: ctx.entity,
    cashBeginMan: openingCashMan,
    loanMonthlyPaymentMan: ctx.loanMonthlyPaymentMan,
    factsCashByMonth: ctx.factsCashByMonthByYear[year] ?? {},
    txns: ctx.txns,
    maps: ctx.maps,
    businessLine: ctx.businessLine,
    txnOverrides: ctx.txnOverrides,
    classifyRules: ctx.classifyRules,
    adjustmentsByMonth: adj,
  });
}

/**
 * 起点年から targetYear まで繰越を連鎖し、targetYear の月次行を返す。
 */
export function buildCashflowWithCarry(
  ctx: CashflowEngineContext,
  targetYear: number
): {
  rows: MqCashflowMonthRow[];
  openingCashMan: number | null;
  settings: MqCashflowSettings | null;
} {
  if (ctx.entity === "combined") {
    const corp = buildCashflowWithCarry(
      { ...ctx, entity: "corporate" },
      targetYear
    );
    const pers = buildCashflowWithCarry(
      { ...ctx, entity: "personal" },
      targetYear
    );
    const merged = mergeCombinedRows(corp.rows, pers.rows);
    return {
      rows: merged,
      openingCashMan:
        corp.openingCashMan != null || pers.openingCashMan != null
          ? (corp.openingCashMan ?? 0) + (pers.openingCashMan ?? 0)
          : null,
      settings: null,
    };
  }

  const line = ctx.businessLine;
  const ent = ctx.entity as "personal" | "corporate";
  const settings = settingsForEntity(ctx.settingsRows, line, ent);

  const origin = originYearOf(settings) ?? targetYear;
  let priorDec: number | null = null;
  let opening: number | null = null;
  let lastRows: MqCashflowMonthRow[] = [];

  for (let y = origin; y <= targetYear; y++) {
    opening = openingForYear(ctx, y, priorDec);
    lastRows = buildCashflowYear(ctx, y, opening);
    priorDec = decemberCashEnd(lastRows);
  }

  return { rows: lastRows, openingCashMan: opening, settings };
}

function addNullable(a: number | null, b: number | null): number | null {
  if (a == null && b == null) return null;
  return (a ?? 0) + (b ?? 0);
}

function mergeCombinedRows(
  a: MqCashflowMonthRow[],
  b: MqCashflowMonthRow[]
): MqCashflowMonthRow[] {
  const byMonth = new Map<string, MqCashflowMonthRow>();
  for (const r of a) byMonth.set(r.month, r);
  return b.map((rb) => {
    const ra = byMonth.get(rb.month);
    if (!ra) return rb;
    const cashEndMan = addNullable(ra.cashEndMan, rb.cashEndMan);
    return {
      month: rb.month,
      cashBeginMan: addNullable(ra.cashBeginMan, rb.cashBeginMan),
      salesMan: addNullable(ra.salesMan, rb.salesMan),
      borrowLtMan: addNullable(ra.borrowLtMan, rb.borrowLtMan),
      borrowStMan: addNullable(ra.borrowStMan, rb.borrowStMan),
      borrowOfficerMan: addNullable(ra.borrowOfficerMan, rb.borrowOfficerMan),
      loanRepaymentMan: addNullable(ra.loanRepaymentMan, rb.loanRepaymentMan),
      repairMan: addNullable(ra.repairMan, rb.repairMan),
      advertisingMan: addNullable(ra.advertisingMan, rb.advertisingMan),
      expenseMan: addNullable(ra.expenseMan, rb.expenseMan),
      managementMan: addNullable(ra.managementMan, rb.managementMan),
      acquisitionMan: addNullable(ra.acquisitionMan, rb.acquisitionMan),
      taxAccountantMan: addNullable(ra.taxAccountantMan, rb.taxAccountantMan),
      annualTaxMan: addNullable(ra.annualTaxMan, rb.annualTaxMan),
      interestYearendMan: addNullable(ra.interestYearendMan, rb.interestYearendMan),
      taxPaymentMan: addNullable(ra.taxPaymentMan, rb.taxPaymentMan),
      actionInflowMan: addNullable(ra.actionInflowMan, rb.actionInflowMan),
      cashEndMan,
      netCashFlowMan: addNullable(ra.netCashFlowMan, rb.netCashFlowMan),
      isNegative: cashEndMan != null && cashEndMan < 0,
      yearendCarryMan: addNullable(ra.yearendCarryMan, rb.yearendCarryMan),
      repaymentRatio:
        ra.repaymentRatio != null && rb.repaymentRatio != null
          ? (ra.repaymentRatio + rb.repaymentRatio) / 2
          : ra.repaymentRatio ?? rb.repaymentRatio,
    };
  });
}

export function negativeMonths(
  rows: MqCashflowMonthRow[]
): { month: string; cashEndMan: number }[] {
  return rows
    .filter((r) => r.isNegative && r.cashEndMan != null)
    .map((r) => ({ month: r.month, cashEndMan: r.cashEndMan! }));
}
