import assert from "node:assert/strict";
import {
  buildLearnRuleFromTxn,
  classifyExpenseTxnHeuristic,
  detectFireInsurance,
  resolveCashflowColumn,
  txnTextBlob,
} from "./mqCashflowClassify";
import { matchBusinessAllowlist } from "./mqCashflowBusinessAllowlist";
import { decemberCashEnd } from "./mqCashflow";
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

// 学習ルール優先 / ホワイトリスト外は除外
{
  const txn = {
    id: 1,
    category: "食費",
    subcategory: "経費",
    entity: "corporate",
    kind: null,
    txn_date: "2025-03-15",
    income_jpy: 0,
    expense_jpy: 280_000,
  };
  const excluded = resolveCashflowColumn(txn, {
    businessLine: "realestate",
    overrides: new Map(),
    rules: [],
  });
  assert.equal(excluded.reason, "excluded");
  assert.equal(excluded.column, null);

  const txn2 = {
    ...txn,
    category: "δ.19F.賃貸経営(法人)",
    subcategory: "保証料",
  };
  const learned = resolveCashflowColumn(txn2, {
    businessLine: "realestate",
    overrides: new Map(),
    rules: [
      {
        business_line: "realestate",
        entity_match: "corporate",
        category_match: "賃貸経営",
        subcategory_match: "保証料",
        cashflow_column: "acquisition",
      },
    ],
  });
  assert.equal(learned.column, "acquisition");
  assert.equal(learned.reason, "learned_rule");
}

// 事業ホワイトリスト — 収入・支出
{
  const rent = matchBusinessAllowlist({
    category: "19.1 家賃収入(個人)",
    subcategory: null,
    entity: "personal",
    kind: null,
    txn_date: "2025-02-01",
    income_jpy: 100_000,
    expense_jpy: 0,
  });
  assert.equal(rent?.side, "income");
  assert.equal(rent?.label, "家賃収入");

  const rentCol = resolveCashflowColumn(
    {
      category: "19.1 家賃収入(法人)",
      subcategory: null,
      entity: "corporate",
      kind: null,
      txn_date: "2025-02-01",
      income_jpy: 200_000,
      expense_jpy: 0,
    },
    { businessLine: "realestate", overrides: new Map(), rules: [] }
  );
  assert.equal(rentCol.column, "sales");
  assert.equal(rentCol.reason, "allowlist");

  const salary = resolveCashflowColumn(
    {
      category: "給与所得",
      subcategory: null,
      entity: "personal",
      kind: null,
      txn_date: "2025-02-01",
      income_jpy: 500_000,
      expense_jpy: 0,
    },
    { businessLine: "realestate", overrides: new Map(), rules: [] }
  );
  assert.equal(salary.reason, "excluded");

  const ai = resolveCashflowColumn(
    {
      category: "δ.21F.AIリスキリング",
      subcategory: "講座",
      entity: "personal",
      kind: null,
      txn_date: "2025-03-01",
      income_jpy: 0,
      expense_jpy: 50_000,
    },
    { businessLine: "realestate", overrides: new Map(), rules: [] }
  );
  assert.equal(ai.column, "expense");
  assert.equal(ai.reason, "allowlist");

  const gamma = resolveCashflowColumn(
    {
      category: "γ.6.2C 自己投資・寄付",
      subcategory: "不動産投資 関連(経費)",
      entity: "personal",
      kind: null,
      txn_date: "2025-03-01",
      income_jpy: 0,
      expense_jpy: 30_000,
    },
    { businessLine: "realestate", overrides: new Map(), rules: [] }
  );
  assert.equal(gamma.column, "expense");

  const d19Repair = resolveCashflowColumn(
    {
      category: "δ.19F.賃貸経営(個人事業)",
      subcategory: "修繕費",
      entity: "personal",
      kind: null,
      txn_date: "2025-04-01",
      income_jpy: 0,
      expense_jpy: 80_000,
    },
    { businessLine: "realestate", overrides: new Map(), rules: [] }
  );
  assert.equal(d19Repair.column, "repair");

  const insurance = resolveCashflowColumn(
    {
      category: "19.6_保険金収入",
      subcategory: null,
      entity: "personal",
      kind: null,
      txn_date: "2025-05-01",
      income_jpy: 1_000_000,
      expense_jpy: 0,
    },
    { businessLine: "realestate", overrides: new Map(), rules: [] }
  );
  assert.equal(insurance.column, "sales");
  assert.equal(insurance.detail, "保険金");
}

// 翌年繰越（事業ホワイトリスト収入で差引が積み上がる）
{
  const rentTxns = Array.from({ length: 12 }, (_, i) => ({
    id: 100 + i,
    category: "19.1 家賃収入(法人)",
    subcategory: null,
    entity: "corporate",
    kind: null,
    txn_date: `2025-${String(i + 1).padStart(2, "0")}-15`,
    income_jpy: 50_000, // 5万円
    expense_jpy: 0,
  }));
  const expenseTxns = Array.from({ length: 12 }, (_, i) => ({
    id: 200 + i,
    category: "δ.19F.賃貸経営(法人)",
    subcategory: "経費",
    entity: "corporate",
    kind: null,
    txn_date: `2025-${String(i + 1).padStart(2, "0")}-20`,
    income_jpy: 0,
    expense_jpy: 30_000, // 3万円
  }));

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
    txns: [...rentTxns, ...expenseTxns],
    maps: [],
    factsCashByMonthByYear: {
      2025: {},
    },
  };

  const y2025 = buildCashflowWithCarry(ctx, 2025);
  assert.equal(y2025.rows[0]?.cashBeginMan, 10);
  const dec = decemberCashEnd(y2025.rows);
  // 期首10 + 12*(5-3) = 34
  assert.equal(dec, 34);

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
    category: "δ.19F.賃貸経営(法人)",
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

  const resolvedAnnual = resolveCashflowColumn(annual, {
    businessLine: "realestate",
    overrides: new Map(),
    rules: [],
  });
  assert.equal(resolvedAnnual.column, "annual_tax");

  const atPurchase = {
    ...annual,
    id: 11,
    description: "取得時 火災保険 初回契約",
  };
  const hPurchase = classifyExpenseTxnHeuristic(atPurchase);
  assert.equal(hPurchase.bucket, "acquisition");
}

console.log("mqCashflowClassify.selftest: ok");
