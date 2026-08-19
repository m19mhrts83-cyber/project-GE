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
  securities: [
    { id: "sbi_index", label: "SBI", band: "sleep" },
  ],
  static_rows: [
    {
      id: "home",
      label: "自宅",
      quadrant: "liability",
      band: "consumer",
    },
  ],
  loan_match: { mini_patterns: ["MINI"], mini_label: "MINIローン", exclude_patterns: ["奨学金"] },
  expense_flow: { exclude_category_patterns: ["奨学金", "15F"] },
  income_categories: ["給与"],
};

const view = composeHouseholdBs({
  year: "2025",
  config: cfg,
  portfolioSnaps: [
    {
      account_id: "sony_life",
      as_of: "2025-08-01",
      value_jpy: 10_000_000,
      source: "test",
    },
    {
      account_id: "sony_life_policy_loan",
      as_of: "2025-08-01",
      value_jpy: 3_000_000,
      source: "test",
    },
  ],
  securitiesSnaps: [
    {
      account_id: "sbi_index",
      as_of: "2025-08-01",
      value_jpy: 5_000_000,
      source: "test",
    },
  ],
  liquiditySnaps: [],
  mqFacts: [],
  loanTracker: [
    {
      id: "mini-1",
      name: "MINI Countryman",
      balance_jpy: 5_000_000,
      category_major: "プライベート",
    },
  ],
  categoryYear: [
    {
      fiscal_year: 2025,
      category: "給与（本業）",
      income_jpy: 8_000_000,
      expense_jpy: 0,
    },
    {
      fiscal_year: 2025,
      category: "15F.奨学金返済",
      income_jpy: 0,
      expense_jpy: 249_576,
    },
  ],
});

const insNet = view.rows.find((r) => r.id === "ins_net_sony_life");
assert(insNet?.amountJpy === 7_000_000, "insurance net");
const policyLoan = view.rows.find((r) => r.id === "policy_loan_sony_life_policy_loan");
assert(policyLoan?.countsTowardTotal === false, "policy loan not in total");
assert(view.totals.assetJpy === 12_000_000, "assets = 7M + 5M sbi");
assert(view.totals.liabilityJpy === 5_000_000, "mini liability");
const mini = view.rows.find((r) => r.id === "loan_mini-1");
assert(mini?.quadrant === "liability", "mini is liability");
assert(!view.rows.some((r) => r.label.includes("奨学金")), "scholarship expense excluded");
assert(view.totals.expenseJpy === 0, "no scholarship in expense total");

console.log("householdBsCompose.selftest: ok");
