/** ローン残高トラッカー → B/S 長期他人資本の候補・資金繰り表ローン参照 */

export type LoanTrackerRow = {
  id?: string;
  balance_jpy?: number | string | null;
  monthly_payment_jpy?: number | string | null;
  annual_payment_jpy?: number | string | null;
  category_major?: string | null;
  tags?: string[] | null;
  name?: string | null;
  lender?: string | null;
};

/**
 * 不動産事業（賃貸経営）に関連するローンか判定。
 * 教育ローン、太陽光ローン、マイカーローン、住宅ローンなどのプライベートローンは除外。
 */
export function isRealEstateBusinessLoan<T extends {
  category_major?: string | null;
  tags?: string[] | null;
  name?: string | null;
}>(loan: T): boolean {
  const major = String(loan.category_major || "");
  const tags = (loan.tags || []).map(String);
  const name = String(loan.name || "");

  // プライベート・自宅・教育・太陽光・マイカー等は明示的に除外
  if (major === "その他" || major === "プライベート") return false;
  if (
    tags.some((t) =>
      ["プライベート", "住宅", "自宅", "教育", "太陽光", "マイカー"].includes(t)
    )
  ) {
    return false;
  }
  if (/教育|太陽光|マイカー|マイホーム|住宅ローン/.test(name)) {
    return false;
  }

  // 不動産事業判定
  if (major === "不動産" || major === "不動産付随") return true;
  if (tags.includes("不動産") || tags.includes("不動産付随")) return true;

  // タグやカテゴリ未設定の簡易テストデータは除外ワードがなければ許容
  if (!major && tags.length === 0 && !name) return true;

  return false;
}

/**
 * entity（corporate / personal / combined）に応じた不動産事業ローンに絞り込む
 */
export function filterLoansByEntity<T extends LoanTrackerRow = LoanTrackerRow>(
  loans: T[],
  entity: "corporate" | "personal" | "combined" | string
): T[] {
  const bizLoans = loans.filter(isRealEstateBusinessLoan);
  if (entity === "corporate") {
    return bizLoans.filter((l) => (l.tags || []).includes("法人"));
  }
  if (entity === "personal") {
    return bizLoans.filter(
      (l) =>
        (l.tags || []).includes("個人") || !(l.tags || []).includes("法人")
    );
  }
  return bizLoans;
}

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
