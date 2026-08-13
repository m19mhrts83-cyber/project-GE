import {
  ROI_ASSETS,
  surfaceYield,
  type RoiAsset,
} from "@/lib/roiAssets";

export type LoanProjectionRow = {
  id: string;
  name: string | null;
  lender: string | null;
  rate_pct: number | string | null;
  balance_jpy: number | string | null;
  monthly_payment_jpy: number | string | null;
  tags?: string[] | null;
  payload?: Record<string, unknown> | null;
};

export type BRate4Row = {
  propertyId: string;
  name: string;
  owner: string;
  surfaceYieldPct: number | null;
  loanRatePct: number | null;
  netSpreadPct: number | null;
  lender: string | null;
  balanceJpy: number | null;
  monthlyPaymentJpy: number | null;
  loanName: string | null;
};

function num(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function matchLoan(asset: RoiAsset, loans: LoanProjectionRow[]): LoanProjectionRow | null {
  const pid = asset.unitPropertyId || asset.id;
  const scored = loans
    .map((loan) => {
      const tags = (loan.tags || []).map(String);
      const payload = (loan.payload || {}) as Record<string, unknown>;
      const propId = String(payload.propertyId || payload.property_id || "");
      let score = 0;
      if (propId === pid || propId === asset.id) score += 10;
      if (tags.includes(pid) || tags.includes(asset.id)) score += 8;
      if ((loan.name || "").includes(asset.name)) score += 5;
      // 諸費用ローンは本担保より低く
      if ((loan.name || "").includes("諸費用")) score -= 3;
      if (String(loan.id || "").includes("cost")) score -= 3;
      return { loan, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score);
  return scored[0]?.loan ?? null;
}

/** B-RATE-4: 保有物件の表面利回り − ローン金利 ≈ 正味 */
export function buildBRate4Rows(loans: LoanProjectionRow[]): BRate4Row[] {
  const owned = ROI_ASSETS.filter((a) => a.status === "owned");
  return owned.map((asset) => {
    const sy = surfaceYield(asset.fullRentBuy, asset.bodyPrice);
    const loan = matchLoan(asset, loans);
    const rate = num(loan?.rate_pct);
    const surfacePct = sy == null ? null : Math.round(sy * 10000) / 100;
    const net =
      surfacePct != null && rate != null
        ? Math.round((surfacePct - rate) * 100) / 100
        : null;
    return {
      propertyId: asset.unitPropertyId || asset.id,
      name: asset.name,
      owner: asset.owner,
      surfaceYieldPct: surfacePct,
      loanRatePct: rate,
      netSpreadPct: net,
      lender: loan?.lender ?? null,
      balanceJpy: num(loan?.balance_jpy),
      monthlyPaymentJpy: num(loan?.monthly_payment_jpy),
      loanName: loan?.name ?? null,
    };
  });
}

export function fmtPct(v: number | null, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}%`;
}
