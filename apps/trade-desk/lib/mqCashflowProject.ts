/**
 * L1 資金繰り行 → L2 MQ facts 相当・L3 B/S 投影
 */

import { computeMq, type MqComputed } from "./mqEquations";
import { roundMan } from "./mqUnits";
import type { MqCashflowMonthRow } from "./mqCashflow";
import { CASHFLOW_COLUMN_BRIDGE } from "./mqCashflowBridge";
import type { CashflowColumnKey } from "./mqCashflowColumns";
import { columnToRowField } from "./mqCashflowColumns";
import type { MqBsFields } from "./mqBs";
import type { MqCashflowSettings } from "./mqCashflowSettings";

export type ProjectedFactMonth = {
  period_month: string;
  pq: number;
  vq: number;
  f: number;
  f_annual: number;
  cash_in: number;
  cash_out: number;
  cash_end: number | null;
};

export type ProjectedBs = MqBsFields & {
  as_of: string;
};

export type CashflowProjectResult = {
  year: number;
  months: ProjectedFactMonth[];
  annual: {
    pq: number;
    vq: number;
    f: number;
    f_annual: number;
    cash_in: number;
    cash_out: number;
    cash_end: number | null;
    cash_begin: number | null;
  };
  computed: MqComputed;
  loanRepaymentMan: number;
  loanExcludedFromG: boolean;
  equationOk: boolean;
  bs: ProjectedBs;
};

function colMan(row: MqCashflowMonthRow, col: CashflowColumnKey): number {
  const field = columnToRowField(col);
  if (!field) return 0;
  const v = row[field];
  return typeof v === "number" && Number.isFinite(v) ? v : 0;
}

export function projectMonth(row: MqCashflowMonthRow): ProjectedFactMonth {
  let pq = 0;
  let vq = 0;
  let f = 0;
  let f_annual = 0;
  let cash_in = 0;
  let cash_out = 0;

  for (const [col, rule] of Object.entries(CASHFLOW_COLUMN_BRIDGE) as [
    CashflowColumnKey,
    (typeof CASHFLOW_COLUMN_BRIDGE)[CashflowColumnKey],
  ][]) {
    const amt = Math.abs(colMan(row, col));
    if (amt === 0) continue;
    if (rule.mq === "pq") pq += amt;
    if (rule.mq === "vq") vq += amt;
    if (rule.mq === "f") f += amt;
    if (rule.mq === "f_annual") f_annual += amt;
    if (rule.cash === "in") cash_in += amt;
    if (rule.cash === "out") cash_out += amt;
  }

  return {
    period_month: row.month,
    pq: roundMan(pq),
    vq: roundMan(vq),
    f: roundMan(f),
    f_annual: roundMan(f_annual),
    cash_in: roundMan(cash_in),
    cash_out: roundMan(cash_out),
    cash_end: row.cashEndMan,
  };
}

export function projectCashflowToMqBs(args: {
  year: number;
  rows: MqCashflowMonthRow[];
  settings: MqCashflowSettings | null;
  priorYearCash?: number | null;
}): CashflowProjectResult {
  const { year, rows, settings } = args;
  const months = rows.map(projectMonth);

  const annual = months.reduce(
    (acc, m) => {
      acc.pq += m.pq;
      acc.vq += m.vq;
      acc.f += m.f;
      acc.f_annual += m.f_annual;
      acc.cash_in += m.cash_in;
      acc.cash_out += m.cash_out;
      return acc;
    },
    {
      pq: 0,
      vq: 0,
      f: 0,
      f_annual: 0,
      cash_in: 0,
      cash_out: 0,
      cash_end: months[11]?.cash_end ?? months[months.length - 1]?.cash_end ?? null,
      cash_begin: rows[0]?.cashBeginMan ?? null,
    }
  );

  const fForMq = roundMan(annual.f + annual.f_annual);
  const computed = computeMq({
    pq: roundMan(annual.pq),
    vq: roundMan(annual.vq),
    f: fForMq,
    q: null,
  });

  const loanRepaymentMan = roundMan(
    rows.reduce((s, r) => s + (r.loanRepaymentMan ?? 0), 0)
  );
  const withLoanInF = computeMq({
    pq: computed.pq,
    vq: computed.vq,
    f: fForMq + loanRepaymentMan,
    q: null,
  });
  const loanExcludedFromG =
    loanRepaymentMan === 0 ||
    Math.abs(computed.g - withLoanInF.g) > 0.4;

  const borrowLt = roundMan(
    rows.reduce((s, r) => s + (r.borrowLtMan ?? 0), 0)
  );
  const borrowSt = roundMan(
    rows.reduce(
      (s, r) =>
        s +
        (r.borrowStMan ?? 0) +
        (r.borrowOfficerMan ?? 0) +
        (r.actionInflowMan ?? 0),
      0
    )
  );
  const acquisition = roundMan(
    rows.reduce((s, r) => s + (r.acquisitionMan ?? 0), 0)
  );
  const taxPay = roundMan(
    rows.reduce((s, r) => s + (r.taxPaymentMan ?? 0), 0)
  );

  const cash = annual.cash_end;
  const capital = settings?.initialCashMan ?? null;
  const current_profit = computed.g;
  const retained_earnings = roundMan(computed.g - taxPay);

  const bs: ProjectedBs = {
    as_of: `${year}-12-31`,
    cash,
    receivables: null,
    inventory: null,
    fixed_assets: acquisition > 0 ? acquisition : null,
    liabilities_st: borrowSt > 0 ? borrowSt : null,
    liabilities_lt:
      borrowLt - loanRepaymentMan !== 0
        ? roundMan(Math.max(0, borrowLt - loanRepaymentMan))
        : null,
    capital,
    retained_earnings,
    current_profit,
  };

  return {
    year,
    months,
    annual: {
      pq: roundMan(annual.pq),
      vq: roundMan(annual.vq),
      f: roundMan(annual.f),
      f_annual: roundMan(annual.f_annual),
      cash_in: roundMan(annual.cash_in),
      cash_out: roundMan(annual.cash_out),
      cash_end: annual.cash_end,
      cash_begin: annual.cash_begin,
    },
    computed,
    loanRepaymentMan,
    loanExcludedFromG,
    equationOk: computed.equationOk,
    bs,
  };
}

export type ReconcileDiff = {
  key: string;
  label: string;
  cashflow: number | null;
  facts: number | null;
  bs: number | null;
  deltaFacts: number | null;
  deltaBs: number | null;
};

export function buildReconcileDiffs(args: {
  project: CashflowProjectResult;
  factsAnnual: {
    pq: number | null;
    vq: number | null;
    f: number | null;
    cash_in: number | null;
    cash_out: number | null;
    cash_end: number | null;
  };
  bsSnap: { cash: number | null; current_profit: number | null } | null;
}): ReconcileDiff[] {
  const { project, factsAnnual, bsSnap } = args;
  const rows: Array<{
    key: string;
    label: string;
    cashflow: number | null;
    facts: number | null;
    bs: number | null;
  }> = [
    {
      key: "pq",
      label: "PQ 売上",
      cashflow: project.annual.pq,
      facts: factsAnnual.pq,
      bs: null,
    },
    {
      key: "vq",
      label: "VQ 変動費",
      cashflow: project.annual.vq,
      facts: factsAnnual.vq,
      bs: null,
    },
    {
      key: "f",
      label: "F 固定費（年払含む）",
      cashflow: roundMan(project.annual.f + project.annual.f_annual),
      facts: factsAnnual.f,
      bs: null,
    },
    {
      key: "g",
      label: "G 利益",
      cashflow: project.computed.g,
      facts: null,
      bs: bsSnap?.current_profit ?? null,
    },
    {
      key: "cash_in",
      label: "入金合計",
      cashflow: project.annual.cash_in,
      facts: factsAnnual.cash_in,
      bs: null,
    },
    {
      key: "cash_out",
      label: "出金合計",
      cashflow: project.annual.cash_out,
      facts: factsAnnual.cash_out,
      bs: null,
    },
    {
      key: "cash_end",
      label: "期末現金",
      cashflow: project.annual.cash_end,
      facts: factsAnnual.cash_end,
      bs: bsSnap?.cash ?? null,
    },
  ];

  return rows.map((r) => ({
    ...r,
    deltaFacts:
      r.cashflow != null && r.facts != null ? r.cashflow - r.facts : null,
    deltaBs: r.cashflow != null && r.bs != null ? r.cashflow - r.bs : null,
  }));
}
