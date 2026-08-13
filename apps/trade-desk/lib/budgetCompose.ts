/** 予算編成シート用。月別計画 × 年次実績の突き合わせ。 */

export type BudgetRow = {
  plan_year: number;
  month: number;
  numbers_category: string;
  category_key: string | null;
  amount_yen: number | string;
};

export type ActualYearCat = {
  fiscal_year: number;
  category: string;
  income_jpy?: number | string | null;
  expense_jpy?: number | string | null;
};

export type BudgetLine = {
  category: string;
  categoryKey: string | null;
  months: number[]; // 12, plan year
  planAnnual: Record<number, number>;
  actualAnnual: Record<number, number | null>;
};

function yen(n: number | string | null | undefined): number {
  const v = Number(n);
  return Number.isFinite(v) ? v : 0;
}

function matchActual(
  category: string,
  categoryKey: string | null,
  actuals: ActualYearCat[],
  year: number
): number | null {
  const yearRows = actuals.filter((a) => a.fiscal_year === year);
  if (!yearRows.length) return null;
  const key = (categoryKey || "").trim();
  const name = category.trim();
  const hit =
    yearRows.find((a) => key && a.category === key) ||
    yearRows.find((a) => name && a.category === name) ||
    yearRows.find(
      (a) => key && (a.category.includes(key) || key.includes(a.category))
    ) ||
    yearRows.find(
      (a) =>
        name &&
        (a.category.includes(name) || name.includes(a.category.split(".")[0] || ""))
    );
  if (!hit) return null;
  const exp = yen(hit.expense_jpy);
  const inc = yen(hit.income_jpy);
  return exp > 0 ? exp : inc;
}

export function composeBudgetLines(
  rows: BudgetRow[],
  actuals: ActualYearCat[],
  planYear: number,
  lookbackYears: number[]
): BudgetLine[] {
  const cats = new Map<string, BudgetLine>();
  for (const r of rows) {
    const cat = (r.numbers_category || r.category_key || "").trim();
    if (!cat) continue;
    if (!cats.has(cat)) {
      cats.set(cat, {
        category: cat,
        categoryKey: r.category_key,
        months: Array(12).fill(0),
        planAnnual: {},
        actualAnnual: {},
      });
    }
    const line = cats.get(cat)!;
    const amt = yen(r.amount_yen);
    if (r.plan_year === planYear && r.month >= 1 && r.month <= 12) {
      line.months[r.month - 1] += amt;
    }
    line.planAnnual[r.plan_year] = (line.planAnnual[r.plan_year] ?? 0) + amt;
  }
  for (const line of cats.values()) {
    for (const y of lookbackYears) {
      line.actualAnnual[y] = matchActual(
        line.category,
        line.categoryKey,
        actuals,
        y
      );
    }
  }
  return [...cats.values()].sort((a, b) =>
    a.category.localeCompare(b.category, "ja")
  );
}

export function yearTotals(lines: BudgetLine[], years: number[]) {
  return years.map((y) => {
    let plan = 0;
    let actual = 0;
    let hasActual = false;
    for (const line of lines) {
      plan += line.planAnnual[y] ?? 0;
      const a = line.actualAnnual[y];
      if (a != null) {
        actual += a;
        hasActual = true;
      }
    }
    return {
      year: y,
      plan,
      actual: hasActual ? actual : null,
    };
  });
}
