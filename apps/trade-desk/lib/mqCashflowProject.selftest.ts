import assert from "node:assert/strict";
import {
  adjustmentsToByMonth,
  mergeActionsIntoAdjustments,
} from "./mqCashflowManual";
import { projectCashflowToMqBs } from "./mqCashflowProject";
import { buildMqCashflowMonthRows } from "./mqCashflow";
import type { MqCashflowMonthRow } from "./mqCashflow";

const months = Array.from({ length: 12 }, (_, i) => `2025-${String(i + 1).padStart(2, "0")}`);

const adj = adjustmentsToByMonth(
  [
    {
      business_line: "realestate",
      entity: "corporate",
      period_month: "2025-12-01",
      field_key: "tax_payment",
      amount_man: 30,
    },
    {
      business_line: "realestate",
      entity: "corporate",
      period_month: "2025-12-01",
      field_key: "interest_yearend",
      amount_man: 5,
    },
  ],
  "realestate",
  "corporate"
);
assert.equal(adj["2025-12"]?.tax_payment, 30);
assert.equal(adj["2025-12"]?.interest_yearend, 5);

const withAction = mergeActionsIntoAdjustments(
  adj,
  [
    {
      business_line: "realestate",
      entity: "corporate",
      period_month: "2025-08-01",
      action_kind: "officer",
      amount_man: 50,
      is_active: true,
    },
  ],
  "realestate",
  "corporate"
);
assert.equal(withAction["2025-08"]?.action_inflow, 50);

const rows = buildMqCashflowMonthRows({
  year: 2025,
  months,
  line: "realestate",
  entity: "corporate",
  cashBeginMan: 10,
  loanMonthlyPaymentMan: null,
  txns: [],
  maps: [],
  adjustmentsByMonth: withAction,
});

assert.equal(rows[0]?.cashBeginMan, 10);
assert.equal(rows[7]?.actionInflowMan, 50);
assert.equal(rows[11]?.taxPaymentMan, 30);
assert.equal(rows[11]?.interestYearendMan, 5);
assert(rows[7]!.cashEndMan! > rows[6]!.cashEndMan!, "action lifts later cash");
assert(rows[11]!.cashEndMan! < rows[10]!.cashEndMan!, "dec tax/interest reduce cash");

const project = projectCashflowToMqBs({
  year: 2025,
  rows,
  settings: {
    businessLine: "realestate",
    entity: "corporate",
    originMonth: "2025-01",
    initialCashMan: 10,
    taxAccrualMonth: "december",
    note: null,
  },
});
assert.equal(project.computed.equationOk, true);
assert.equal(project.annual.cash_in, 50);
assert.equal(project.loanExcludedFromG, true);
assert.equal(project.bs.capital, 10);
assert.equal(project.bs.current_profit, project.computed.g);

// ローン元本は F/G に入れない
const withLoan: MqCashflowMonthRow[] = rows.map((r, i) =>
  i === 0 ? { ...r, loanRepaymentMan: 20, netCashFlowMan: (r.netCashFlowMan ?? 0) - 20 } : r
);
const p2 = projectCashflowToMqBs({
  year: 2025,
  rows: withLoan,
  settings: null,
});
assert.equal(p2.loanRepaymentMan, 20);
assert.equal(p2.computed.g, project.computed.g);

console.log("mqCashflowProject.selftest: ok");
