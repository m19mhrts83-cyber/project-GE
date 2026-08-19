/**
 * householdReFiled.selftest.ts
 */
import { householdFiledReFromMetrics } from "./householdReFiled";
import type { TaxYearMetricRow } from "./taxInsights";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

const metrics: TaxYearMetricRow[] = [
  {
    scope: "personal",
    fiscal_year: 2024,
    filing_status: "filed",
    filed_on: null,
    note: null,
    source: "catalog",
    taxable_income_jpy: null,
    income_tax_jpy: null,
    refund_or_pay: null,
    revenue_jpy: null,
    ordinary_income_jpy: null,
    corporate_tax_jpy: null,
    tax_payable_jpy: null,
    payload: { re_revenue_jpy: 5_948_140, source_pdf: "2024年度/令和6年分収支内訳書（不動産所得用）.pdf" },
  },
  {
    scope: "personal",
    fiscal_year: 2026,
    filing_status: "draft",
    filed_on: null,
    note: null,
    source: null,
    taxable_income_jpy: null,
    income_tax_jpy: null,
    refund_or_pay: null,
    revenue_jpy: null,
    ordinary_income_jpy: null,
    corporate_tax_jpy: null,
    tax_payable_jpy: null,
    payload: {},
  },
];

const filed2024 = householdFiledReFromMetrics(metrics, 2024);
assert(filed2024.personalRevenueJpy === 5_948_140, "2024 revenue");
assert(filed2024.useFiledInTotals === true, "2024 filed");

const draft2026 = householdFiledReFromMetrics(metrics, 2026);
assert(draft2026.useFiledInTotals === false, "2026 not filed");
assert(draft2026.personalRevenueJpy === null, "2026 no revenue");

console.log("householdReFiled.selftest: ok");
