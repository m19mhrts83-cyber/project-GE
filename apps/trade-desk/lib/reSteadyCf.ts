/** ③: 満室想定 CF と、一時費用を除いた定常の実 CF。 */

import { stripAbgPrefix } from "@/lib/lifeplanBoard";
import {
  ROI_ASSETS,
  groupUnitsLive,
  type PropertyUnitRow,
  type RoiAsset,
} from "@/lib/roiAssets";

export type ReTxn = {
  category: string | null;
  subcategory: string | null;
  txn_date: string | null;
  income_jpy: number | string | null;
  expense_jpy: number | string | null;
};

export type SpecialKind =
  | "acquisition_tax"
  | "property_tax"
  | "repair"
  | "insurance"
  | "leasing"
  | "corp_tax"
  | "other_special";

export const SPECIAL_LABEL: Record<SpecialKind, string> = {
  acquisition_tax: "不動産取得税",
  property_tax: "固定資産税・租税公課",
  repair: "修繕",
  insurance: "火災保険",
  leasing: "広告・客付",
  corp_tax: "法人税",
  other_special: "その他特別",
};

export type ReExpBucket = "loan" | "opex" | "special" | "income";

export type ReSteadyBoard = {
  year: number;
  throughMonth: number;
  throughLabel: string;
  assumedRentMonth: number;
  assumedPayMonth: number;
  assumedCfMonth: number;
  liveOccupied: number;
  liveTotal: number;
  liveRentMonth: number;
  actualRentMonth: number | null;
  actualLoanMonth: number | null;
  actualOpexMonth: number | null;
  steadyCfMonth: number | null;
  accountingCfMonth: number | null;
  rentGapMonth: number | null;
  cfGapMonth: number | null;
  specialYtd: number;
  specials: { kind: SpecialKind; yen: number }[];
  annualSteady: number | null;
  coverRatio: number | null;
  coverShortfall: number | null;
  rentYtd: number;
  loanYtd: number;
  opexYtd: number;
  allExpYtd: number;
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

export function isReFinanceCat(category: string): boolean {
  const c = stripAbgPrefix(category);
  if (!c || c === "合計") return false;
  return (
    c.startsWith("19") ||
    c.includes("不動産") ||
    c.includes("マンション") ||
    c.includes("家賃") ||
    c.includes("賃貸")
  );
}

export function classifySpecialKind(sub: string): SpecialKind | null {
  const s = sub.trim();
  if (!s) return null;
  if (s.includes("取得税")) return "acquisition_tax";
  if (s.includes("固定資産") || s.includes("租税公課")) return "property_tax";
  if (s.includes("修繕")) return "repair";
  if (s.includes("火災保険")) return "insurance";
  if (s.includes("広告") || s.includes("商品券")) return "leasing";
  if (s.includes("法人税")) return "corp_tax";
  return null;
}

export function classifyReExp(subcategory: string | null): ReExpBucket {
  const s = (subcategory || "").trim();
  if (classifySpecialKind(s)) return "special";
  if (s.includes("ローン")) return "loan";
  return "opex";
}

export function ownedRoiAssets(assets: RoiAsset[] = ROI_ASSETS): RoiAsset[] {
  return assets.filter((a) => a.status === "owned");
}

export function assumedFromRoi(assets: RoiAsset[] = ROI_ASSETS): {
  rentMonth: number;
  payMonth: number;
  cfMonth: number;
} {
  let rentMonth = 0;
  let payMonth = 0;
  for (const a of ownedRoiAssets(assets)) {
    rentMonth += (a.fullRentBuy ?? 0) / 12;
    payMonth += a.monthlyPayNow ?? a.monthlyPayBuy ?? 0;
  }
  return {
    rentMonth,
    payMonth,
    cfMonth: rentMonth - payMonth,
  };
}

export function composeReSteadyBoard(
  txns: ReTxn[],
  unitRows: PropertyUnitRow[],
  year: number,
  throughMonth: number,
  assets: RoiAsset[] = ROI_ASSETS
): ReSteadyBoard {
  const assumed = assumedFromRoi(assets);
  const liveMap = groupUnitsLive(unitRows);
  let liveOccupied = 0;
  let liveTotal = 0;
  let liveRentMonth = 0;
  for (const g of liveMap.values()) {
    liveOccupied += g.occupied;
    liveTotal += g.total;
    liveRentMonth += g.occupiedRentMonth;
  }

  let rentYtd = 0;
  let loanYtd = 0;
  let opexYtd = 0;
  let specialYtd = 0;
  const specialMap = new Map<SpecialKind, number>();

  for (const t of txns) {
    const cat = (t.category || "").trim();
    if (!isReFinanceCat(cat)) continue;
    const m = monthOf(t.txn_date);
    if (m == null || m > throughMonth) continue;
    const inc = yen(t.income_jpy);
    const exp = yen(t.expense_jpy);
    if (inc > 0) rentYtd += inc;
    if (exp <= 0) continue;
    const sub = t.subcategory || "";
    const kind = classifySpecialKind(sub);
    if (kind) {
      specialYtd += exp;
      specialMap.set(kind, (specialMap.get(kind) ?? 0) + exp);
      continue;
    }
    if (classifyReExp(sub) === "loan") loanYtd += exp;
    else opexYtd += exp;
  }

  const months = Math.max(1, throughMonth);
  const hasActual = rentYtd > 0 || loanYtd > 0 || opexYtd > 0;
  const actualRentMonth = hasActual ? rentYtd / months : null;
  const actualLoanMonth = hasActual ? loanYtd / months : null;
  const actualOpexMonth = hasActual ? opexYtd / months : null;
  const steadyCfMonth = hasActual
    ? (rentYtd - loanYtd - opexYtd) / months
    : null;
  const allExpYtd = loanYtd + opexYtd + specialYtd;
  const accountingCfMonth = hasActual ? (rentYtd - allExpYtd) / months : null;
  const rentGapMonth =
    actualRentMonth != null ? assumed.rentMonth - actualRentMonth : null;
  const cfGapMonth =
    steadyCfMonth != null ? assumed.cfMonth - steadyCfMonth : null;
  const annualSteady = steadyCfMonth != null ? steadyCfMonth * 12 : null;
  const coverRatio =
    annualSteady != null && specialYtd > 0 ? annualSteady / specialYtd : null;
  const coverShortfall =
    annualSteady != null ? specialYtd - annualSteady : null;

  const specials = [...specialMap.entries()]
    .map(([kind, yenAmt]) => ({ kind, yen: yenAmt }))
    .sort((a, b) => b.yen - a.yen);

  return {
    year,
    throughMonth,
    throughLabel: `1〜${throughMonth}月`,
    assumedRentMonth: assumed.rentMonth,
    assumedPayMonth: assumed.payMonth,
    assumedCfMonth: assumed.cfMonth,
    liveOccupied,
    liveTotal,
    liveRentMonth,
    actualRentMonth,
    actualLoanMonth,
    actualOpexMonth,
    steadyCfMonth,
    accountingCfMonth,
    rentGapMonth,
    cfGapMonth,
    specialYtd,
    specials,
    annualSteady,
    coverRatio,
    coverShortfall,
    rentYtd,
    loanYtd,
    opexYtd,
    allExpYtd,
  };
}
