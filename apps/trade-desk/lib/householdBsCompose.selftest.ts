/**
 * householdBsCompose.selftest.ts
 * Run: npx tsx lib/householdBsCompose.selftest.ts
 */
import { composeHouseholdBs, type HouseholdConfig } from "./householdBsCompose";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

const cfg: HouseholdConfig = {
  insurance_pairs: [
    {
      gross_id: "sony_life",
      loan_id: "sony_life_policy_loan",
      label: "ソニー生命",
    },
  ],
  securities: [{ id: "sbi_index", label: "SBI", band: "sleep" }],
  static_rows: [],
  loan_match: { mini_patterns: ["MINI"], mini_label: "MINI", exclude_patterns: ["奨学金"] },
  expense_flow: { exclude_category_patterns: ["奨学金", "15F", "合計", "19", "賃貸", "マンション"] },
  income_categories: ["給与"],
};

const taxMetrics = [
  {
    scope: "personal",
    fiscal_year: 2025,
    filing_status: "filed",
    filed_on: null,
    note: null,
    source: "test",
    taxable_income_jpy: null,
    income_tax_jpy: null,
    refund_or_pay: null,
    revenue_jpy: null,
    ordinary_income_jpy: null,
    corporate_tax_jpy: null,
    tax_payable_jpy: null,
    payload: { re_revenue_jpy: 4_371_840 },
  },
] as import("./taxInsights").TaxYearMetricRow[];

const view2025 = composeHouseholdBs({
  year: "2025",
  config: cfg,
  portfolioSnaps: [],
  securitiesSnaps: [],
  liquiditySnaps: [],
  mqFacts: [],
  loanTracker: [],
  categoryYear: [
    {
      fiscal_year: 2025,
      category: "給与（本業）",
      income_jpy: 8_000_000,
      expense_jpy: 0,
    },
    {
      fiscal_year: 2025,
      category: "19.2不労所得(売却)",
      income_jpy: 100_000,
      expense_jpy: 0,
    },
  ],
  propertyUnits: [
    {
      property_id: "grandole-ii",
      property_name: "G2",
      room: "201",
      status: "occupied",
      rent: 40_000,
      note: null,
      payload: { management_fee: 2_000, total_rent: 42_000 },
    },
  ],
  taxMetrics,
});

assert(
  view2025.rows.find((r) => r.id === "re_rent_filed_personal")?.amountJpy === 4_371_840,
  "filed revenue 2025"
);
assert(
  view2025.rows.find((r) => r.id === "re_rent_gross")?.countsTowardTotal === false,
  "occupancy not in total when filed"
);
assert(view2025.totals.expenseJpy === 0, "no mgmt expense when filed");

const view2026 = composeHouseholdBs({
  year: "2026",
  config: cfg,
  portfolioSnaps: [],
  securitiesSnaps: [],
  liquiditySnaps: [],
  mqFacts: [],
  loanTracker: [],
  categoryYear: [],
  propertyUnits: [
    {
      property_id: "grandole-ii",
      property_name: "G2",
      room: "201",
      status: "occupied",
      rent: 40_000,
      note: null,
      payload: { management_fee: 2_000, total_rent: 42_000 },
    },
  ],
  taxMetrics,
});

assert(
  view2026.rows.some((r) => r.id === "re_rent_gross" && r.countsTowardTotal),
  "2026 uses occupancy"
);

console.log("householdBsCompose.selftest: ok");
