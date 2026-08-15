/**
 * mqIngestApply.selftest.ts
 */
import { planMqIngestUpserts } from "./mqIngestApply";
import type { MonthBucket } from "./mqZaimMap";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

const buckets: MonthBucket[] = [
  {
    business_line: "realestate",
    entity: "corporate",
    period_month: "2026-01-01",
    pq: 100,
    vq: 10,
    f: 5,
    f_annual: 0,
    cash_in: 100,
    cash_out: 15,
  },
  {
    business_line: "realestate",
    entity: "personal",
    period_month: "2026-02-01",
    pq: 50,
    vq: 0,
    f: 0,
    f_annual: 0,
    cash_in: 50,
    cash_out: 0,
  },
];

const existing = [
  {
    id: "manual-1",
    business_line: "realestate",
    entity: "corporate",
    period_month: "2026-01-01",
    source: "manual",
    scenario_kind: "actual",
  },
  {
    id: "stale-1",
    business_line: "ai",
    entity: "personal",
    period_month: "2026-03-01",
    source: "import",
    scenario_kind: "actual",
  },
];

const plan = planMqIngestUpserts(buckets, existing, { year: 2026 });
assert(plan.skippedManualMonths.includes("realestate|corporate|2026-01"), "manual skip");
assert(plan.toUpsert.length === 1, "one upsert");
assert(plan.toUpsert[0].period_month === "2026-02-01", "feb upsert");
assert(plan.staleImportIds.includes("stale-1"), "stale deleted");

const forced = planMqIngestUpserts(buckets, existing, { year: 2026, force: true });
assert(forced.toUpsert.length === 2, "force overwrites manual");

console.log("mqIngestApply.selftest: ok");
