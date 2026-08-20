import assert from "node:assert/strict";
import {
  buildLearnRuleFromTxn,
  classifyExpenseTxnHeuristic,
  detectFireInsurance,
  resolveCashflowColumn,
  txnTextBlob,
} from "./mqCashflowClassify";
import { buildMqCashflowMonthRows, decemberCashEnd } from "./mqCashflow";
import { buildCashflowWithCarry } from "./mqCashflowEngine";
import { openingCashFromSettings } from "./mqCashflowSettings";

// 起点 2025-01 · 期首10万
{
  const settings = {
    businessLine: "realestate",
    entity: "corporate" as const,
    originMonth: "2025-01",
    initialCashMan: 10,
    taxAccrualMonth: "december" as const,
    note: null,
  };
  assert.equal(openingCashFromSettings(settings, 2025), 10);
  assert.equal(openingCashFromSettings(settings, 2026), null);
}

// 学習ルール優先
{
  const txn = {
    id: 1,
    category: "賃貸",
    subcategory: "経費",
    entity: "corporate",
    kind: null,
    txn_date: "2025-03-15",
    income_jpy: 0,
    expense_jpy: 280_000,
  };
  const h = classifyExpenseTxnHeuristic(txn);
  assert.equal(h.bucket, "expense");

  const resolved = resolveCashflowColumn(txn, {
    businessLine: "realestate",
    overrides: new Map(),
    rules: [
      {
        business_line: "realestate",
        entity_match: "corporate",
        category_match: "賃貸",
        subcategory_match: "保証料",
        cashflow_column: "acquisition",
      },
    ],
  });
  assert.equal(resolved.reason, "heuristic");

  const txn2 = { ...txn, subcategory: "保証料" };
  const learned = resolveCashflowColumn(txn2, {
    businessLine: "realestate",
    overrides: new Map(),
    rules: [
      {
        business_line: "realestate",
        entity_match: "corporate",
        category_match: "賃貸",
        subcategory_match: "保証料",
        cashflow_column: "acquisition",
      },
    ],
  });
  assert.equal(learned.column, "acquisition");
  assert.equal(learned.reason, "learned_rule");
}

// 翌年繰越
{
  const ctx = {
    businessLine: "realestate",
    entity: "corporate" as const,
    settingsRows: [
      {
        business_line: "realestate",
        entity: "corporate" as const,
        origin_month: "2025-01-01",
        initial_cash_man: 10,
      },
    ],
    txnOverrides: [],
    classifyRules: [],
    loanMonthlyPaymentMan: null,
    txns: [],
    maps: [],
    factsCashByMonthByYear: {
      2025: Object.fromEntries(
        Array.from({ length: 12 }, (_, i) => {
          const mo = `2025-${String(i + 1).padStart(2, "0")}`;
          return [
            mo,
            { cashInMan: 5, cashOutMan: 3, cashEndMan: null },
          ] as const;
        })
      ),
    },
  };

  const y2025 = buildCashflowWithCarry(ctx, 2025);
  assert.equal(y2025.rows[0]?.cashBeginMan, 10);
  const dec = decemberCashEnd(y2025.rows);
  assert(dec != null && dec > 10, "should accumulate");

  const y2026 = buildCashflowWithCarry(ctx, 2026);
  assert.equal(y2026.openingCashMan, dec);
  assert.equal(y2026.rows[0]?.cashBeginMan, dec);
}

// learn rule payload
{
  const rule = buildLearnRuleFromTxn(
    {
      category: "賃貸",
      subcategory: "保証料",
      entity: "corporate",
      kind: null,
      txn_date: "2025-01-01",
      income_jpy: 0,
      expense_jpy: 1,
    },
    "realestate",
    "acquisition",
    99
  );
  assert.equal(rule.cashflow_column, "acquisition");
  assert.equal(rule.category_match, "賃貸");
}

// 火災保険 — 摘要のみでも検出、年払は annualTax
{
  const annual = {
    id: 10,
    category: "19F",
    subcategory: "経費",
    entity: "corporate",
    kind: null,
    txn_date: "2025-04-01",
    income_jpy: 0,
    expense_jpy: 320_000,
    description: "Grandole I 火災保険 年払更新",
  };
  assert(detectFireInsurance(txnTextBlob(annual)));
  const hAnnual = classifyExpenseTxnHeuristic(annual);
  assert.equal(hAnnual.bucket, "annualTax");

  const atPurchase = {
    ...annual,
    id: 11,
    description: "取得時 火災保険 初回契約",
  };
  const hPurchase = classifyExpenseTxnHeuristic(atPurchase);
  assert.equal(hPurchase.bucket, "acquisition");
}

console.log("mqCashflowClassify.selftest: ok");
