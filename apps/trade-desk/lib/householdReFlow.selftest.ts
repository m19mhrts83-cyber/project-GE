/**
 * householdReFlow.selftest.ts
 * Run: npx tsx lib/householdReFlow.selftest.ts
 */
import {
  buildHouseholdReFlow,
  householdReMonthsOwned,
  isHouseholdReOtherIncome,
} from "./householdReFlow";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

assert(householdReMonthsOwned(2024, "2022-09", new Date("2026-08-19")) === 12, "g2 2024 full");
assert(householdReMonthsOwned(2025, "2025-02-28", new Date("2026-08-19")) === 10, "g1 2025 from Mar");
assert(householdReMonthsOwned(2025, "2025-12-26", new Date("2026-08-19")) === 0, "caramel 2025 none");
assert(householdReMonthsOwned(2026, "2025-12-26", new Date("2026-08-19")) === 8, "caramel 2026 elapsed");
assert(householdReMonthsOwned(2026, "2022-09", new Date("2026-08-19")) === 8, "g2 2026 elapsed");

assert(isHouseholdReOtherIncome("19.2不労所得(売却)") === true, "sale");
assert(isHouseholdReOtherIncome("19.1 家賃収入(個人)") === false, "rent net skipped");
assert(isHouseholdReOtherIncome("19.6_保険金収入") === true, "insurance");

const flow = buildHouseholdReFlow({
  year: 2026,
  asOf: new Date("2026-08-19"),
  units: [
    {
      property_id: "grandole-ii",
      property_name: "G2",
      room: "201",
      status: "occupied",
      rent: 50_000,
      note: null,
      payload: { management_fee: 2_000, total_rent: 52_000 },
    },
  ],
});
assert(flow.properties.length === 1, "one owned with months");
assert(flow.properties[0].months === 8, "8 months");
assert(flow.properties[0].grossJpy === 52_000 * 8, "gross");
assert(flow.properties[0].mgmtJpy === 2_000 * 8, "mgmt");
assert(flow.totals.grossJpy === 52_000 * 8, "total gross");

console.log("householdReFlow.selftest: ok");
