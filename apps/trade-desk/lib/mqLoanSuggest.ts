/** ローン残高トラッカー → B/S 長期他人資本の候補 */

export type LoanTrackerRow = {
  balance_jpy?: number | string | null;
  category_major?: string | null;
  tags?: string[] | null;
  name?: string | null;
};

/** 投資用不動産ローン等の残高合計（null行は無視） */
export function sumLoanTrackerLt(rows: LoanTrackerRow[]): number | null {
  let sum = 0;
  let any = false;
  for (const r of rows) {
    const b = r.balance_jpy;
    if (b == null || b === "") continue;
    const n = Number(b);
    if (!Number.isFinite(n)) continue;
    sum += n;
    any = true;
  }
  return any ? Math.round(sum) : null;
}
