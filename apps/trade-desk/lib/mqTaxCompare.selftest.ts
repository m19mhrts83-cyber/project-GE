/**
 * mqTaxCompare.selftest.ts
 * Run: npx tsx lib/mqTaxCompare.selftest.ts
 */
import { buildMqTaxCompare, buildMqTaxCompareDual, taxScopeForMq } from "./mqTaxCompare";
import { computeMq } from "./mqEquations";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

assert(taxScopeForMq("realestate", "personal") === "personal", "personal scope");
assert(taxScopeForMq("realestate", "corporate") === "corporate", "corp scope");
assert(taxScopeForMq("realestate", "combined") === null, "combined null");

const computed = computeMq({ pq: 437, vq: 50, f: 380, q: 12 });
const compare = buildMqTaxCompare({
  line: "realestate",
  entity: "personal",
  fiscalYear: 2025,
  computed,
  depreciationMan: 120,
  metric: {
    scope: "personal",
    fiscal_year: 2025,
    filing_status: "filed",
    filed_on: "2026-03-01",
    note: null,
    source: "import",
    taxable_income_jpy: 7305000,
    income_tax_jpy: 795410,
    refund_or_pay: "refund",
    revenue_jpy: null,
    ordinary_income_jpy: null,
    corporate_tax_jpy: null,
    tax_payable_jpy: null,
    payload: {
      re_income_jpy: -1538030,
      re_revenue_jpy: 4371840,
      re_income_statement_jpy: -1811310,
    },
  },
});

assert(compare != null, "compare built");
assert(compare!.rows.length >= 4, "rows");
const g = compare!.rows.find((r) => r.id === "g");
assert(g?.mqMan === computed.g, "g mq");
assert(g?.filedMan === -154, "g filed man rounded");
assert(g?.diffMan === g!.mqMan! - g!.filedMan!, "g diff");

const dual = buildMqTaxCompareDual({
  line: "realestate",
  fiscalYear: 2025,
  personal: {
    computed,
    depreciationMan: 120,
    metric: {
      scope: "personal",
      fiscal_year: 2025,
      filing_status: "filed",
      filed_on: "2026-03-01",
      note: null,
      source: "import",
      taxable_income_jpy: 7305000,
      income_tax_jpy: 795410,
      refund_or_pay: "refund",
      revenue_jpy: null,
      ordinary_income_jpy: null,
      corporate_tax_jpy: null,
      tax_payable_jpy: null,
      payload: {
        re_income_jpy: -1538030,
        re_revenue_jpy: 4371840,
      },
    },
  },
  corporate: {
    computed: computeMq({ pq: 200, vq: 30, f: 150, q: 0 }),
    depreciationMan: 80,
    metric: {
      scope: "corporate",
      fiscal_year: 2025,
      filing_status: "filed",
      filed_on: "2026-05-20",
      note: null,
      source: "import",
      taxable_income_jpy: null,
      income_tax_jpy: null,
      refund_or_pay: null,
      revenue_jpy: 20000000,
      ordinary_income_jpy: 5000000,
      corporate_tax_jpy: 1000000,
      tax_payable_jpy: 1000000,
      payload: {},
    },
  },
});
assert(dual?.entity === "combined", "dual entity");
assert(dual?.personal != null && dual?.corporate != null, "dual both");

console.log("mqTaxCompare.selftest: ok");
