import assert from "node:assert/strict";
import { normalizeBs, type MqBsRow } from "./mqBs";
import {
  buildEquityTrend,
  combineProjectedEquityBs,
  equityDelta,
  yearsForEquityTrend,
} from "./mqEquityTrend";

function snap(partial: Partial<MqBsRow> & Pick<MqBsRow, "as_of_date" | "entity">): MqBsRow {
  return {
    business_line: "realestate",
    cash: null,
    receivables: null,
    inventory: null,
    fixed_assets: null,
    liabilities_st: null,
    liabilities_lt: null,
    capital: 10,
    retained_earnings: 0,
    current_profit: 5,
    ...partial,
  };
}

const snap2025 = snap({
  entity: "corporate",
  as_of_date: "2025-12-31",
  source: "manual",
});

{
  const years = yearsForEquityTrend({
    bsRows: [snap2025],
    line: "realestate",
    originYear: 2025,
    throughYear: 2026,
  });
  assert.deepEqual(years, [2025, 2026]);
}

{
  const points = buildEquityTrend({
    years: [2025, 2026],
    bsRows: [snap2025],
    line: "realestate",
    entity: "corporate",
    projectedByYear: {
      2026: normalizeBs({
        capital: 10,
        retained_earnings: 5,
        current_profit: 8,
      }),
    },
  });
  assert.equal(points[0]!.source, "snapshot");
  assert.equal(points[0]!.equityMan, 15);
  assert.equal(points[1]!.source, "cashflow_project");
  assert.equal(points[1]!.equityMan, 23);
  assert.equal(equityDelta(points), 8);
}

{
  const points = buildEquityTrend({
    years: [2026],
    bsRows: [snap2025],
    line: "realestate",
    entity: "corporate",
  });
  assert.equal(points[0]!.source, "missing");
  assert.equal(points[0]!.equityMan, null);
}

{
  const points = buildEquityTrend({
    years: [2025],
    bsRows: [snap2025],
    line: "realestate",
    entity: "combined",
  });
  assert.equal(points[0]!.source, "snapshot");
  assert.equal(points[0]!.note, "個人・法人の片方のみ");
  assert.equal(points[0]!.equityMan, 15);
}

{
  const combined = combineProjectedEquityBs(
    normalizeBs({ capital: 10, retained_earnings: 1, current_profit: 2 }),
    normalizeBs({ capital: null, retained_earnings: 3, current_profit: 4 })
  );
  assert.ok(combined);
  assert.equal(combined.capital, 10);
  assert.equal(combined.retained_earnings, 4);
  assert.equal(combined.current_profit, 6);
}

{
  const points = buildEquityTrend({
    years: [2025],
    bsRows: [
      snap({
        entity: "corporate",
        as_of_date: "2025-06-30",
        current_profit: null,
        retained_earnings: 2,
      }),
    ],
    line: "realestate",
    entity: "corporate",
    mqGByYear: { 2025: 9 },
  });
  assert.equal(points[0]!.source, "snapshot");
  assert.equal(points[0]!.equityMan, 21);
  assert.equal(points[0]!.profitMan, 9);
}

{
  const points = buildEquityTrend({
    years: [2025],
    bsRows: [],
    line: "all",
    entity: "corporate",
    projectedByYear: {
      2025: normalizeBs({ capital: 10, retained_earnings: 0, current_profit: 1 }),
    },
  });
  assert.equal(points[0]!.source, "missing");
  assert.match(String(points[0]!.note), /全体/);
}

console.log("mqEquityTrend.selftest: ok");
