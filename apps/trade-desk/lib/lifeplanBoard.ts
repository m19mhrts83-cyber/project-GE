/** ホーム②: ライフプラン計画 vs 財務実績（家計支出）。 */

export type BoardBudgetRow = {
  version_id?: string;
  plan_year: number;
  month: number;
  numbers_category: string;
  category_key: string | null;
  amount_yen: number | string;
};

export type BoardTxn = {
  category: string | null;
  txn_date: string | null;
  expense_jpy: number | string | null;
};

export type LifeplanBoard = {
  year: number;
  throughMonth: number;
  throughLabel: string;
  actualThroughLabel: string | null;
  planAnnual: number;
  planYtd: number;
  actualYtd: number | null;
  gapYtd: number | null;
};

function yen(n: number | string | null | undefined): number {
  const v = Number(n);
  return Number.isFinite(v) ? v : 0;
}

function monthOf(iso: string | null): number | null {
  if (!iso || iso.length < 7) return null;
  const m = Number(iso.slice(5, 7));
  return Number.isFinite(m) && m >= 1 && m <= 12 ? m : null;
}

/** Zaim 取引は `β.2C.食費`、ライフプラン表1は `2C.食費`。 */
export function stripAbgPrefix(cat: string): string {
  return cat.replace(/^[αβγδε]\./, "").trim();
}

function isPlanCat(cat: string, keys: Set<string>): boolean {
  const c = stripAbgPrefix(cat);
  if (!c || c === "合計") return false;
  if (c.startsWith("19") || c.startsWith("0.")) return false;
  return keys.has(c);
}

export function composeLifeplanBoard(
  budgetRows: BoardBudgetRow[],
  txns: BoardTxn[],
  year: number,
  throughMonth: number
): LifeplanBoard {
  let planAnnual = 0;
  let planYtd = 0;
  const keys = new Set<string>();
  for (const r of budgetRows) {
    if (r.plan_year !== year) continue;
    const key = (r.category_key || "").trim();
    if (key) keys.add(key);
    const amt = yen(r.amount_yen);
    if (r.month >= 1 && r.month <= 12) planAnnual += amt;
    if (r.month >= 1 && r.month <= throughMonth) planYtd += amt;
  }

  let actualYtd = 0;
  let hasActual = false;
  let maxDate: string | null = null;
  for (const t of txns) {
    const cat = (t.category || "").trim();
    if (!isPlanCat(cat, keys)) continue;
    const m = monthOf(t.txn_date);
    if (m == null || m > throughMonth) continue;
    actualYtd += yen(t.expense_jpy);
    hasActual = true;
    if (t.txn_date && (!maxDate || t.txn_date > maxDate)) maxDate = t.txn_date;
  }

  const throughLabel = `1〜${throughMonth}月`;
  let actualThroughLabel: string | null = null;
  if (maxDate && maxDate.length >= 10) {
    const md = `${Number(maxDate.slice(5, 7))}/${Number(maxDate.slice(8, 10))}`;
    actualThroughLabel = `${throughLabel} 実績（〜${md}）`;
  }

  return {
    year,
    throughMonth,
    throughLabel,
    actualThroughLabel,
    planAnnual,
    planYtd,
    actualYtd: hasActual ? actualYtd : null,
    gapYtd: hasActual ? actualYtd - planYtd : null,
  };
}
