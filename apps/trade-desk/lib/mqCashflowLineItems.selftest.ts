import assert from "node:assert/strict";
import {
  buildCellDetailResponse,
  buildCashflowLineItems,
  isLineItemReclassifiable,
  lineItemDisplayTag,
  lineItemsForCell,
} from "./mqCashflowLineItems";

const txns = [
  {
    id: 1,
    category: "δ.19F.賃貸経営(法人)",
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
    category: "δ.19F.賃貸経営(法人)",
    subcategory: "保証料",
    entity: "corporate",
    kind: null,
    txn_date: "2025-03-12",
    income_jpy: 0,
    expense_jpy: 280_000,
    description: "△△保証料",
  },
  {
    id: 3,
    category: "δ.19F.賃貸経営(法人)",
    subcategory: "その他",
    entity: "corporate",
    kind: null,
    txn_date: "2025-03-20",
    income_jpy: 0,
    expense_jpy: 350_000,
    description: "LEAF 火災保険",
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
      category_match: "賃貸経営",
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

const insuranceMarch = lineItemsForCell(items, "2025-03", "annual_tax");
assert.equal(insuranceMarch.length, 1);
assert.equal(lineItemDisplayTag(insuranceMarch[0]!), "火災保険");

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

// ローン重複排除・プライベートローン除外の検証
const testLoans = [
  {
    id: "corp-loan-1",
    name: "Grandole志賀本通Ⅰ",
    lender: "オリックス銀行",
    monthly_payment_jpy: 260_000,
    category_major: "不動産",
    tags: ["不動産", "法人"],
  },
  {
    id: "edu-loan",
    name: "教育ローン（名古屋銀行）",
    lender: "名古屋銀行",
    monthly_payment_jpy: 23_000,
    category_major: "その他",
    tags: ["プライベート", "個人", "教育"],
  },
  {
    id: "solar-loan",
    name: "太陽光ローン（オリコ）",
    lender: "オリコ",
    monthly_payment_jpy: 8_000,
    category_major: "その他",
    tags: ["プライベート", "個人", "太陽光"],
  },
];

const txnsWithLoan = [
  ...txns,
  {
    id: 10,
    category: "δ.19F.賃貸経営(法人)",
    subcategory: "ローン返済(法人)",
    entity: "corporate",
    kind: null,
    txn_date: "2025-03-10",
    income_jpy: 0,
    expense_jpy: 260_000,
    description: "オリックス返済",
  },
];

const itemsWithLoans = buildCashflowLineItems({
  year: 2025,
  entity: "corporate",
  businessLine: "realestate",
  txns: txnsWithLoan,
  loanTracker: testLoans,
  loanMonthlyPaymentMan: 26,
});

// 2025-03 には Zaim の実績返済取引（id: 10）があるので、loan_tracker 由来の手動行は重複追加されない！
const loansMarch = lineItemsForCell(itemsWithLoans, "2025-03", "loan_repayment");
assert.equal(loansMarch.length, 1);
assert.equal(loansMarch[0]?.source, "txn");
assert.equal(loansMarch[0]?.amountMan, -26);

// 実績取引のない 2025-04 には、事業ローン（Grandole志賀本通Ⅰ）のみが手動参照行として補完され、教育・太陽光は除外される！
const loansApril = lineItemsForCell(itemsWithLoans, "2025-04", "loan_repayment");
assert.equal(loansApril.length, 1);
assert.equal(loansApril[0]?.source, "loan_tracker");
assert.equal(loansApril[0]?.place, "オリックス銀行 · Grandole志賀本通Ⅰ");
assert.equal(loansApril[0]?.amountMan, -26);

console.log("mqCashflowLineItems.selftest: ok");
