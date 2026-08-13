/** ③-A: Zaim 投影 `kurashift_finance_category_year` から個人／法人／合算を集計。 */

export type FinanceCategoryYearRow = {
  fiscal_year: number;
  category: string | null;
  income_jpy: number | null;
  expense_jpy: number | null;
  net_jpy: number | null;
};

export type ReCfBucket = {
  income: number;
  expense: number;
  cf: number;
  categories: string[];
};

function isRe19(cat: string): boolean {
  return (
    cat.startsWith("19") ||
    cat.includes("不動産") ||
    cat.includes("マンション") ||
    cat.includes("家賃") ||
    cat.includes("賃貸")
  );
}

function isCorp(cat: string): boolean {
  return cat.includes("法人");
}

function isPersonal(cat: string): boolean {
  if (isCorp(cat)) return false;
  // 明示「個人」または 19系で法人表記なし（LUUP・保険金等は個人側）
  if (cat.includes("個人")) return true;
  if (isRe19(cat)) return true;
  return false;
}

export function emptyReCfBucket(): ReCfBucket {
  return { income: 0, expense: 0, cf: 0, categories: [] };
}

export function combineReCf(a: ReCfBucket, b: ReCfBucket): ReCfBucket {
  return {
    income: a.income + b.income,
    expense: a.expense + b.expense,
    cf: a.cf + b.cf,
    categories: [...a.categories, ...b.categories],
  };
}

export function aggregateReCfFromCategoryYear(
  rows: FinanceCategoryYearRow[],
  fiscalYear: number
): { personal: ReCfBucket; corporate: ReCfBucket; combined: ReCfBucket } {
  const personal = emptyReCfBucket();
  const corporate = emptyReCfBucket();

  for (const r of rows) {
    if (r.fiscal_year !== fiscalYear) continue;
    const cat = (r.category || "").trim();
    if (!cat || !isRe19(cat)) continue;
    const inc = Number(r.income_jpy) || 0;
    const exp = Number(r.expense_jpy) || 0;
    const bucket = isCorp(cat) ? corporate : isPersonal(cat) ? personal : null;
    if (!bucket) continue;
    bucket.income += inc;
    bucket.expense += exp;
    bucket.categories.push(cat);
  }
  personal.cf = personal.income - personal.expense;
  corporate.cf = corporate.income - corporate.expense;
  return { personal, corporate, combined: combineReCf(personal, corporate) };
}

/** 当年経過月数（最低1）。月次ランレート用。Asia/Tokyo。 */
export function tokyoYmd(now = new Date()): {
  year: number;
  month: number;
  day: number;
} {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  return {
    year: Number(parts.find((p) => p.type === "year")?.value),
    month: Number(parts.find((p) => p.type === "month")?.value),
    day: Number(parts.find((p) => p.type === "day")?.value),
  };
}

export function monthsElapsedInYear(now = new Date()): number {
  return Math.max(1, tokyoYmd(now).month);
}

/** 月次ランレート用。当月20日未満なら前月まで（未完了月を割らない）。 */
export function completeMonthsElapsed(now = new Date()): number {
  const { month, day } = tokyoYmd(now);
  if (day >= 20) return Math.max(1, month);
  return Math.max(1, month - 1);
}
