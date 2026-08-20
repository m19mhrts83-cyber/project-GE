import assert from "node:assert/strict";
import {
  buildCellDetailResponse,
  buildCashflowLineItems,
  isLineItemReclassifiable,
  lineItemsForCell,
} from "./mqCashflowLineItems";

const txns = [
  {
    id: 1,
    category: "賃貸",
    subcategory: "経費",
    entity: "corporate",
    kind: null,
    txn_date: "2025-03-05",
    income_jpy: 0,
    expense_jpy: 120_000,
    description: "○○設備",
  },
  {
    id: 2,
    category: "賃貸",
    subcategory: "保証料",
    entity: "corporate",
    kind: null,
    txn_date: "2025-03-12",
    income_jpy: 0,
    expense_jpy: 280_000,
    description: "△△保証料",
  },
];

const items = buildCashflowLineItems({
  year: 2025,
  entity: "corporate",
  businessLine: "realestate",
  txns,
  classifyRules: [
    {
      business_line: "realestate",
      entity_match: "corporate",
      category_match: "賃貸",
      subcategory_match: "保証料",
      cashflow_column: "acquisition",
    },
  ],
});

const expenseMarch = lineItemsForCell(items, "2025-03", "expense");
assert.equal(expenseMarch.length, 1);
assert.equal(expenseMarch[0]?.place, "○○設備");

const acqMarch = lineItemsForCell(items, "2025-03", "acquisition");
assert.equal(acqMarch.length, 1);
assert.equal(acqMarch[0]?.classifyReason, "learned_rule");

const detail = buildCellDetailResponse({
  month: "2025-03",
  columnKey: "expense",
  cellTotalMan: 15,
  items,
});
assert.equal(detail.header.txnCount, 1);
assert(detail.items.some((it) => it.source === "residual"), "residual when cell differs");
assert.equal(detail.reclassifiable, true);

assert.equal(isLineItemReclassifiable(expenseMarch[0]!), true);
assert.equal(
  isLineItemReclassifiable(
    detail.items.find((it) => it.source === "residual")!
  ),
  false
);

console.log("mqCashflowLineItems.selftest: ok");
