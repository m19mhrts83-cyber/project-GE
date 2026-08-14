/** 確定申告ページ用：Zaim気配・前年差・気づき。申告所得そのものではない。 */

import { aggregateReCfFromCategoryYear, type FinanceCategoryYearRow } from "@/lib/reFinanceYtd";

export type TaxScope = "personal" | "corporate";

export type TaxYearMetricPayload = {
  re_income_jpy?: number | string | null;
  re_income_statement_jpy?: number | string | null;
  re_revenue_jpy?: number | string | null;
  withholding_jpy?: number | string | null;
  refund_amount_jpy?: number | string | null;
  [key: string]: unknown;
};

export type TaxYearMetricRow = {
  scope: string;
  fiscal_year: number;
  filing_status: string | null;
  filed_on: string | null;
  note: string | null;
  source: string | null;
  taxable_income_jpy: number | string | null;
  income_tax_jpy: number | string | null;
  refund_or_pay: string | null;
  revenue_jpy: number | string | null;
  ordinary_income_jpy: number | string | null;
  corporate_tax_jpy: number | string | null;
  tax_payable_jpy: number | string | null;
  payload?: TaxYearMetricPayload | null;
};

export type TaxPrepHint = {
  fiscalYear: number;
  reIncome: number;
  reExpense: number;
  reCf: number;
  /** 表示用。常にこの注記を添える */
  disclaimer: string;
};

export type TaxYearView = {
  fiscalYear: number;
  label: string;
  hasMetrics: boolean;
  hasCaseReady: boolean;
  evidenceCount: number;
  prep: TaxPrepHint | null;
  /** 第一表の不動産所得（確定） */
  filedReIncome: number | null;
  /** 気配CF − 確定不動産所得 */
  zaimVsFiledDiff: number | null;
  /** 差 ÷ |確定|。確定が0のときは null */
  zaimVsFiledPct: number | null;
  taxableIncome: number | null;
  incomeTax: number | null;
  refundOrPay: string | null;
  revenue: number | null;
  ordinaryIncome: number | null;
  corporateTax: number | null;
  taxPayable: number | null;
  filingStatus: string | null;
  filedOn: string | null;
  note: string | null;
  deltaTax: number | null;
  deltaTaxPct: number | null;
  deltaIncome: number | null;
  insights: string[];
};

const DISCLAIMER =
  "Zaim投影の気配（不動産CF）。確定申告の所得そのものではありません。";

export function yen(n: number | string | null | undefined): number | null {
  if (n == null || n === "") return null;
  const v = Number(n);
  return Number.isFinite(v) ? v : null;
}

export function yearLabel(scope: TaxScope, year: number): string {
  return scope === "corporate" ? `${year}年5月期` : `${year}年分`;
}

export function yearOptions(scope: TaxScope, currentYear: number, count = 5): number[] {
  const out: number[] = [];
  for (let i = 0; i < count; i++) out.push(currentYear - i);
  return out;
}

export function prepHintForYear(
  scope: TaxScope,
  fiscalYear: number,
  categoryRows: FinanceCategoryYearRow[]
): TaxPrepHint | null {
  if (scope !== "personal") return null;
  const { personal } = aggregateReCfFromCategoryYear(categoryRows, fiscalYear);
  if (personal.income === 0 && personal.expense === 0) return null;
  return {
    fiscalYear,
    reIncome: personal.income,
    reExpense: personal.expense,
    reCf: personal.cf,
    disclaimer: DISCLAIMER,
  };
}

function filedReIncomeFromMetric(m: TaxYearMetricRow | undefined): number | null {
  if (!m?.payload) return null;
  return yen(m.payload.re_income_jpy);
}

export function zaimVsFiled(
  prepCf: number | null | undefined,
  filedRe: number | null | undefined
): { diff: number | null; pct: number | null } {
  if (prepCf == null || filedRe == null) return { diff: null, pct: null };
  const diff = prepCf - filedRe;
  if (filedRe === 0) return { diff, pct: null };
  return { diff, pct: diff / Math.abs(filedRe) };
}

function taxAmount(scope: TaxScope, m: TaxYearMetricRow | undefined): number | null {
  if (!m) return null;
  if (scope === "personal") return yen(m.income_tax_jpy);
  return yen(m.tax_payable_jpy) ?? yen(m.corporate_tax_jpy);
}

function incomeAmount(scope: TaxScope, m: TaxYearMetricRow | undefined): number | null {
  if (!m) return null;
  if (scope === "personal") return yen(m.taxable_income_jpy);
  return yen(m.ordinary_income_jpy);
}

export function buildTaxYearViews(args: {
  scope: TaxScope;
  years: number[];
  metrics: TaxYearMetricRow[];
  categoryRows: FinanceCategoryYearRow[];
  caseReadyYears: Set<number>;
  evidenceCountByYear: Map<number, number>;
  inWindow: boolean;
  currentCycleYear: number;
}): TaxYearView[] {
  const byYear = new Map<number, TaxYearMetricRow>();
  for (const m of args.metrics) {
    if (m.scope !== args.scope) continue;
    byYear.set(m.fiscal_year, m);
  }

  const views: TaxYearView[] = args.years.map((y) => {
    const m = byYear.get(y);
    const prep = prepHintForYear(args.scope, y, args.categoryRows);
    const filedReIncome = filedReIncomeFromMetric(m);
    const vs = zaimVsFiled(prep?.reCf ?? null, filedReIncome);
    return {
      fiscalYear: y,
      label: yearLabel(args.scope, y),
      hasMetrics: !!m,
      hasCaseReady: args.caseReadyYears.has(y),
      evidenceCount: args.evidenceCountByYear.get(y) ?? 0,
      prep,
      filedReIncome,
      zaimVsFiledDiff: vs.diff,
      zaimVsFiledPct: vs.pct,
      taxableIncome: yen(m?.taxable_income_jpy),
      incomeTax: yen(m?.income_tax_jpy),
      refundOrPay: m?.refund_or_pay ?? null,
      revenue: yen(m?.revenue_jpy),
      ordinaryIncome: yen(m?.ordinary_income_jpy),
      corporateTax: yen(m?.corporate_tax_jpy),
      taxPayable: yen(m?.tax_payable_jpy),
      filingStatus: m?.filing_status ?? null,
      filedOn: m?.filed_on ?? null,
      note: m?.note ?? null,
      deltaTax: null,
      deltaTaxPct: null,
      deltaIncome: null,
      insights: [],
    };
  });

  for (let i = 0; i < views.length; i++) {
    const cur = views[i];
    const prev = views[i + 1]; // years are descending
    if (!prev) continue;
    const curTax = taxAmount(args.scope, byYear.get(cur.fiscalYear));
    const prevTax = taxAmount(args.scope, byYear.get(prev.fiscalYear));
    const curInc = incomeAmount(args.scope, byYear.get(cur.fiscalYear));
    const prevInc = incomeAmount(args.scope, byYear.get(prev.fiscalYear));
    if (curTax != null && prevTax != null) {
      cur.deltaTax = curTax - prevTax;
      cur.deltaTaxPct = prevTax === 0 ? null : (curTax - prevTax) / Math.abs(prevTax);
    }
    if (curInc != null && prevInc != null) {
      cur.deltaIncome = curInc - prevInc;
    }
  }

  for (const v of views) {
    v.insights = buildInsights({
      scope: args.scope,
      view: v,
      inWindow: args.inWindow && v.fiscalYear === args.currentCycleYear,
    });
  }

  return views;
}

function buildInsights(args: {
  scope: TaxScope;
  view: TaxYearView;
  inWindow: boolean;
}): string[] {
  const out: string[] = [];
  const v = args.view;

  if (!v.hasMetrics) {
    if (args.scope === "corporate" && v.evidenceCount > 0) {
      out.push("証憑はあるが決算KPI未登録。結果を登録すると前年比較できます。");
    } else if (args.scope === "personal" && v.hasCaseReady) {
      out.push("弥生CSVはあるが申告結果KPI未登録。申告後に税額を登録してください。");
    } else if (args.inWindow) {
      out.push(
        args.scope === "corporate"
          ? "取込窓です。大野さんメール取込またはKPI登録を進めてください。"
          : "申告シーズンです。弥生CSV作成と結果登録を進めてください。"
      );
    } else {
      out.push("結果KPI未登録。推移を見るには1年分の登録が必要です。");
    }
  }

  if (v.deltaTaxPct != null && Math.abs(v.deltaTaxPct) >= 0.2) {
    const dir = v.deltaTaxPct > 0 ? "増加" : "減少";
    out.push(`税額が前年比${dir}（約${Math.round(Math.abs(v.deltaTaxPct) * 100)}%）。要因をメモに残すとよいです。`);
  }

  if (
    args.scope === "corporate" &&
    v.ordinaryIncome != null &&
    v.deltaIncome != null &&
    v.deltaIncome < 0 &&
    v.deltaTax != null &&
    v.deltaTax > 0
  ) {
    out.push("利益は減っているのに税額が増えています。確認してください。");
  }

  if (args.scope === "personal" && v.prep && v.prep.reCf < 0) {
    out.push("不動産CF気配がマイナスです。申告後にライフプラン年次も見直せます。");
  }

  if (
    args.scope === "personal" &&
    v.zaimVsFiledPct != null &&
    Math.abs(v.zaimVsFiledPct) >= 0.2
  ) {
    const dir = v.zaimVsFiledDiff != null && v.zaimVsFiledDiff > 0 ? "上振れ" : "下振れ";
    out.push(
      `気配が確定不動産所得より${dir}（約${Math.round(Math.abs(v.zaimVsFiledPct) * 100)}%）。減価償却・借入利息の差を疑うとよいです。`
    );
  }

  return out.slice(0, 3);
}

export function refundLabel(v: string | null): string {
  if (v === "refund") return "還付";
  if (v === "pay") return "納付";
  if (v === "zero") return "ゼロ";
  return "—";
}
