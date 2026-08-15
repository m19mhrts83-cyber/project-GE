/**
 * aggregateRows の再帰防止・事業線内訳
 * Run: npx tsx lib/mqAggregate.selftest.ts
 */
import {
  aggregateRows,
  filterFactsMonth,
  type MqFactRow,
} from "./mqAggregate";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

const base = {
  id: "t1",
  entity: "corporate",
  period_month: "2026-01-01",
  scenario_kind: "actual",
  plan_variant_id: "",
  q: 1,
  pq: 825,
  vq: 454,
  f: 332,
  f_annual: 0,
  cash_in: null,
  cash_out: null,
  cash_end: 39,
  depreciation_jpy: null,
} as const;

const oneLine: MqFactRow[] = [
  { ...base, business_line: "realestate" },
];

const twoLines: MqFactRow[] = [
  { ...base, id: "re", business_line: "realestate", pq: 800, vq: 400, f: 300 },
  {
    ...base,
    id: "ai",
    business_line: "ai",
    entity: "personal",
    pq: 100,
    vq: 20,
    f: 50,
    q: 2,
  },
];

const a = aggregateRows(oneLine, "month");
assert(a.computed, "oneLine computed");
assert(a.byLine.length === 1, "oneLine byLine count");
assert(a.byLine[0].line === "realestate", "oneLine byLine line");
assert(a.computed.pq === 825, "oneLine pq");

const b = aggregateRows(twoLines, "month");
assert(b.computed, "twoLines computed");
assert(b.byLine.length === 2, "twoLines byLine count");
assert(b.computed.pq === 900, "twoLines pq sum");

const subset = filterFactsMonth(oneLine, "realestate", "combined", "2026-01");
const c = aggregateRows(subset, "month");
assert(c.computed, "filtered computed");
assert(c.cashEnd === 39, "cashEnd");

console.log("mqAggregate.selftest: ok");
