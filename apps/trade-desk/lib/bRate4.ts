import {
  ROI_ASSETS,
  surfaceYield,
  type RoiAsset,
} from "@/lib/roiAssets";
import { loansForProperty } from "@/lib/rePropertyMaster";

export type LoanProjectionRow = {
  id: string;
  name: string | null;
  lender: string | null;
  rate_pct: number | string | null;
  balance_jpy: number | string | null;
  monthly_payment_jpy: number | string | null;
  tags?: string[] | null;
  category_major?: string | null;
  payload?: Record<string, unknown> | null;
};

export type LoanBlendPart = {
  id: string;
  name: string | null;
  lender: string | null;
  ratePct: number;
  balanceJpy: number;
  weightPct: number;
  monthlyPaymentJpy: number | null;
};

export type BRate4Row = {
  propertyId: string;
  name: string;
  owner: string;
  surfaceYieldPct: number | null;
  /** 合算金利（残高加重）。単一ローンならその金利 */
  loanRatePct: number | null;
  /** 正味 = 表面 − 合算金利 */
  netSpreadPct: number | null;
  /** 参考: 本担保のみの金利 */
  primaryLoanRatePct: number | null;
  lender: string | null;
  balanceJpy: number | null;
  monthlyPaymentJpy: number | null;
  loanName: string | null;
  loanCount: number;
  excludedMissingBalance: number;
  parts: LoanBlendPart[];
};

function num(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/**
 * 残高加重平均金利:
 *   r_eff = Σ(B_i × r_i) / Σ(B_i)
 * 残高または金利が欠けるローンは除外（呼び出し側で件数を返す）。
 */
export function blendLoanRate(loans: LoanProjectionRow[]): {
  ratePct: number | null;
  balanceJpy: number | null;
  monthlyPaymentJpy: number | null;
  parts: LoanBlendPart[];
  excludedMissingBalance: number;
} {
  const parts: LoanBlendPart[] = [];
  let excluded = 0;
  let sumBal = 0;
  let sumWeighted = 0;
  let sumPay = 0;
  let hasPay = false;

  for (const loan of loans) {
    const rate = num(loan.rate_pct);
    const bal = num(loan.balance_jpy);
    if (rate == null || bal == null || bal <= 0) {
      excluded += 1;
      continue;
    }
    sumBal += bal;
    sumWeighted += bal * rate;
    const pay = num(loan.monthly_payment_jpy);
    if (pay != null) {
      sumPay += pay;
      hasPay = true;
    }
    parts.push({
      id: loan.id,
      name: loan.name,
      lender: loan.lender,
      ratePct: rate,
      balanceJpy: bal,
      weightPct: 0,
      monthlyPaymentJpy: pay,
    });
  }

  if (sumBal <= 0 || parts.length === 0) {
    return {
      ratePct: null,
      balanceJpy: null,
      monthlyPaymentJpy: null,
      parts: [],
      excludedMissingBalance: excluded,
    };
  }

  for (const p of parts) {
    p.weightPct = round2((p.balanceJpy / sumBal) * 100);
  }

  return {
    ratePct: round2(sumWeighted / sumBal),
    balanceJpy: Math.round(sumBal),
    monthlyPaymentJpy: hasPay ? Math.round(sumPay) : null,
    parts,
    excludedMissingBalance: excluded,
  };
}

/** 本担保（諸費用・cost 以外でスコア最高）を1本選ぶ（参考表示用） */
function matchPrimaryLoan(
  asset: RoiAsset,
  loans: LoanProjectionRow[]
): LoanProjectionRow | null {
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
      if ((loan.name || "").includes("諸費用")) score -= 3;
      if (String(loan.id || "").includes("cost")) score -= 3;
      return { loan, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score);
  return scored[0]?.loan ?? null;
}

/**
 * B-RATE-4: 保有物件の表面利回り − 合算ローン金利 ≈ 正味
 * 合算は物件紐づけローンの残高加重平均（docs/KURASHIFT_loan_tracker_Discover.md）。
 */
export function buildBRate4Rows(loans: LoanProjectionRow[]): BRate4Row[] {
  const owned = ROI_ASSETS.filter((a) => a.status === "owned");
  return owned.map((asset) => {
    const propertyId = asset.unitPropertyId || asset.id;
    const sy = surfaceYield(asset.fullRentBuy, asset.bodyPrice);
    const surfacePct = sy == null ? null : round2(sy * 100);

    const linked = loansForProperty(propertyId, loans);
    const blend = blendLoanRate(linked);
    const primary = matchPrimaryLoan(asset, linked);
    const primaryRate = num(primary?.rate_pct);

    const net =
      surfacePct != null && blend.ratePct != null
        ? round2(surfacePct - blend.ratePct)
        : null;

    const lenderLabel =
      blend.parts.length > 1
        ? `${blend.parts.length}本合算`
        : blend.parts[0]?.lender ?? primary?.lender ?? null;

    const nameLabel =
      blend.parts.length > 1
        ? blend.parts.map((p) => p.name || p.id).join(" + ")
        : blend.parts[0]?.name ?? primary?.name ?? null;

    return {
      propertyId,
      name: asset.name,
      owner: asset.owner,
      surfaceYieldPct: surfacePct,
      loanRatePct: blend.ratePct,
      netSpreadPct: net,
      primaryLoanRatePct: primaryRate,
      lender: lenderLabel,
      balanceJpy: blend.balanceJpy,
      monthlyPaymentJpy: blend.monthlyPaymentJpy,
      loanName: nameLabel,
      loanCount: blend.parts.length,
      excludedMissingBalance: blend.excludedMissingBalance,
      parts: blend.parts,
    };
  });
}

export function fmtPct(v: number | null, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}%`;
}
