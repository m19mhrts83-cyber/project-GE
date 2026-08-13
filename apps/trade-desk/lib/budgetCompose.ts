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

export type BudgetSection = "education" | "realestate" | "household" | "income";

export type BudgetLine = {
  category: string;
  categoryKey: string | null;
  section: BudgetSection;
  months: number[]; // 12, plan year
  planAnnual: Record<number, number>;
  actualAnnual: Record<number, number | null>;
  /** 収入側の実績（不動産家賃など）。支出費目は null */
  actualIncomeAnnual?: Record<number, number | null>;
  fromPlan: boolean;
};

export const SECTION_LABEL: Record<BudgetSection, string> = {
  education: "教育（内訳）",
  realestate: "不動産（内訳）",
  household: "家計・その他",
  income: "収入（参考）",
};

export const SECTION_ORDER: BudgetSection[] = [
  "education",
  "realestate",
  "household",
  "income",
];

function yen(n: number | string | null | undefined): number {
  const v = Number(n);
  return Number.isFinite(v) ? v : 0;
}

/** Zaim / 予算キーの比較用。αβγδε 接頭辞と空白差を落とす。 */
export function normCat(cat: string | null | undefined): string {
  return (cat || "")
    .replace(/^[αβγδε]\./, "")
    .replace(/\s+/g, "")
    .trim();
}

export function sectionFor(categoryKey: string | null, category: string): BudgetSection {
  const blob = `${categoryKey || ""} ${category || ""}`;
  const n = normCat(blob);
  if (
    /^0\./.test(n) ||
    /給与|賞与|児童手当|税還付|臨時収入|キャッシュバック|返金/.test(blob)
  ) {
    return "income";
  }
  if (
    n.startsWith("19") ||
    /不動産|家賃|賃貸|マンション経営/.test(blob)
  ) {
    return "realestate";
  }
  if (
    /10\.[0-9]|こども|学資|教育|学費/.test(blob) ||
    n.startsWith("10.")
  ) {
    return "education";
  }
  return "household";
}

function matchActualRow(
  category: string,
  categoryKey: string | null,
  actuals: ActualYearCat[],
  year: number
): ActualYearCat | null {
  const yearRows = actuals.filter((a) => a.fiscal_year === year);
  if (!yearRows.length) return null;
  const keyN = normCat(categoryKey);
  const nameN = normCat(category);
  const hit =
    yearRows.find((a) => keyN && normCat(a.category) === keyN) ||
    yearRows.find((a) => nameN && normCat(a.category) === nameN) ||
    yearRows.find(
      (a) =>
        keyN &&
        (normCat(a.category).includes(keyN) || keyN.includes(normCat(a.category)))
    ) ||
    yearRows.find(
      (a) =>
        nameN &&
        (normCat(a.category).includes(nameN) ||
          nameN.includes(normCat(a.category)))
    );
  return hit || null;
}

function actualExpense(hit: ActualYearCat | null): number | null {
  if (!hit) return null;
  const exp = yen(hit.expense_jpy);
  const inc = yen(hit.income_jpy);
  if (exp > 0) return exp;
  if (inc > 0) return null; // 収入専用は expense 側に載せない
  return 0;
}

function actualIncome(hit: ActualYearCat | null): number | null {
  if (!hit) return null;
  const inc = yen(hit.income_jpy);
  return inc > 0 ? inc : null;
}

function lineKey(category: string, categoryKey: string | null): string {
  return normCat(categoryKey) || normCat(category) || category;
}

/**
 * 計画行を軸にしつつ、実績にだけある教育・不動産費目も行として足す。
 */
export function composeBudgetLines(
  rows: BudgetRow[],
  actuals: ActualYearCat[],
  planYear: number,
  lookbackYears: number[]
): BudgetLine[] {
  const cats = new Map<string, BudgetLine>();

  const ensure = (
    category: string,
    categoryKey: string | null,
    fromPlan: boolean
  ): BudgetLine => {
    const k = lineKey(category, categoryKey);
    let line = cats.get(k);
    if (!line) {
      line = {
        category,
        categoryKey,
        section: sectionFor(categoryKey, category),
        months: Array(12).fill(0),
        planAnnual: {},
        actualAnnual: {},
        actualIncomeAnnual: {},
        fromPlan,
      };
      cats.set(k, line);
    } else if (fromPlan) {
      line.fromPlan = true;
      if (categoryKey && !line.categoryKey) line.categoryKey = categoryKey;
      // 表示名は計画側を優先
      if (fromPlan && category) line.category = category;
      line.section = sectionFor(line.categoryKey, line.category);
    }
    return line;
  };

  for (const r of rows) {
    const cat = (r.numbers_category || r.category_key || "").trim();
    if (!cat) continue;
    const line = ensure(cat, r.category_key, true);
    const amt = yen(r.amount_yen);
    if (r.plan_year === planYear && r.month >= 1 && r.month <= 12) {
      line.months[r.month - 1] += amt;
    }
    line.planAnnual[r.plan_year] = (line.planAnnual[r.plan_year] ?? 0) + amt;
  }

  // 実績だけの教育・不動産（＋収入参考）を足す
  const yearsForExtras = [...new Set([...lookbackYears, planYear])];
  for (const a of actuals) {
    if (!yearsForExtras.includes(a.fiscal_year)) continue;
    const cat = (a.category || "").trim();
    if (!cat || cat === "合計") continue;
    const sec = sectionFor(cat, cat);
    if (sec !== "education" && sec !== "realestate" && sec !== "income") {
      continue;
    }
    const k = lineKey(cat, cat);
    if (cats.has(k)) continue;
    // 既存計画キーと部分一致するならスキップ（二重行防止）
    const already = [...cats.values()].some((line) => {
      const nk = normCat(line.categoryKey);
      const nc = normCat(line.category);
      const na = normCat(cat);
      return (nk && (nk === na || nk.includes(na) || na.includes(nk))) ||
        (nc && (nc === na || nc.includes(na) || na.includes(nc)));
    });
    if (already) continue;
    ensure(cat, cat, false);
  }

  for (const line of cats.values()) {
    for (const y of lookbackYears) {
      const hit = matchActualRow(line.category, line.categoryKey, actuals, y);
      const exp = actualExpense(hit);
      const inc = actualIncome(hit);
      // 支出が無い収入行は income を actualAnnual に載せる（表で1列に見せる）
      if (line.section === "income" || (exp == null && inc != null)) {
        line.actualAnnual[y] = inc;
        line.actualIncomeAnnual![y] = inc;
      } else {
        line.actualAnnual[y] = exp;
        line.actualIncomeAnnual![y] = inc;
      }
    }
  }

  return [...cats.values()].sort((a, b) => {
    const sa = SECTION_ORDER.indexOf(a.section);
    const sb = SECTION_ORDER.indexOf(b.section);
    if (sa !== sb) return sa - sb;
    return (a.categoryKey || a.category).localeCompare(
      b.categoryKey || b.category,
      "ja"
    );
  });
}

export function groupBySection(lines: BudgetLine[]): {
  section: BudgetSection;
  label: string;
  lines: BudgetLine[];
}[] {
  return SECTION_ORDER.map((section) => ({
    section,
    label: SECTION_LABEL[section],
    lines: lines.filter((l) => l.section === section),
  })).filter((g) => g.lines.length > 0);
}

/** 棒グラフ用。家計＋教育の支出合計（不動産・収入は別枠なので混ぜない）。 */
export function yearTotals(lines: BudgetLine[], years: number[]) {
  return years.map((y) => {
    let plan = 0;
    let actual = 0;
    let hasActual = false;
    for (const line of lines) {
      if (line.section === "realestate" || line.section === "income") continue;
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

/** 2026予算確認向け: 直近4年（例: 2022–2025）。 */
export function budgetLookbackYears(planYear: number): number[] {
  return [planYear - 4, planYear - 3, planYear - 2, planYear - 1];
}
