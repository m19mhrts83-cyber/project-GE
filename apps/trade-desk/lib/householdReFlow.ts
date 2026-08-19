/**
 * 家計B/Sの不動産フロー。
 * 正本の考え方: docs/KURASHIFT_家計BS_不動産フロー.md
 * 号室・家賃・管理費: property_units（内容確認／③-C）
 */
import { RE_PROPERTY_MASTER } from "@/lib/rePropertyMaster";
import { unitBreakdown, type PropertyUnitRow } from "@/lib/roiAssets";

export type HouseholdRePropertyLine = {
  id: string;
  label: string;
  owner: string;
  months: number;
  rentJpy: number;
  mgmtJpy: number;
  grossJpy: number;
};

export type HouseholdReFlow = {
  asOf: string;
  year: number;
  monthsInScope: number;
  properties: HouseholdRePropertyLine[];
  totals: { rentJpy: number; mgmtJpy: number; grossJpy: number };
  basis: string;
};

function parseAcquired(acquired: string): Date {
  const s = acquired.trim();
  if (/^\d{4}-\d{2}$/.test(s)) return new Date(`${s}-01T00:00:00`);
  return new Date(`${s.slice(0, 10)}T00:00:00`);
}

/** 所有開始が月半ば超なら翌月から数える（決済月末はほぼ0ヶ月）。 */
export function householdReMonthsOwned(
  year: number,
  acquiredIso: string,
  asOf: Date = new Date()
): number {
  const acquired = parseAcquired(acquiredIso);
  if (Number.isNaN(acquired.getTime())) return 0;
  const yearStart = new Date(year, 0, 1);
  const endExclusive =
    year === asOf.getFullYear()
      ? new Date(asOf.getFullYear(), asOf.getMonth() + 1, 1)
      : new Date(year + 1, 0, 1);
  let from = acquired > yearStart ? new Date(acquired) : yearStart;
  if (acquired.getFullYear() === year && acquired.getDate() > 15) {
    from = new Date(acquired.getFullYear(), acquired.getMonth() + 1, 1);
  }
  if (from >= endExclusive) return 0;
  return (
    (endExclusive.getFullYear() - from.getFullYear()) * 12 +
    (endExclusive.getMonth() - from.getMonth())
  );
}

export function buildHouseholdReFlow(args: {
  year: number;
  units: PropertyUnitRow[];
  asOf?: Date;
}): HouseholdReFlow {
  const asOf = args.asOf ?? new Date();
  const properties: HouseholdRePropertyLine[] = [];
  let rentJpy = 0;
  let mgmtJpy = 0;
  let grossJpy = 0;
  const currentMonths =
    args.year === asOf.getFullYear() ? asOf.getMonth() + 1 : 12;

  for (const prop of RE_PROPERTY_MASTER) {
    const months = householdReMonthsOwned(args.year, prop.acquired, asOf);
    if (months <= 0) continue;
    let rentM = 0;
    let mgmtM = 0;
    let grossM = 0;
    for (const u of args.units) {
      if (u.property_id !== prop.id || u.status !== "occupied") continue;
      const b = unitBreakdown(u);
      const rent = b.rent ?? 0;
      const gross = b.totalRent ?? rent + (b.mgmt ?? 0);
      const mgmt = b.mgmt ?? Math.max(0, gross - rent);
      rentM += rent;
      mgmtM += mgmt;
      grossM += gross;
    }
    if (grossM <= 0 && rentM <= 0) continue;
    const rent = Math.round(rentM * months);
    const mgmt = Math.round(mgmtM * months);
    const gross = Math.round(grossM * months);
    properties.push({
      id: prop.id,
      label: prop.name,
      owner: prop.owner,
      months,
      rentJpy: rent,
      mgmtJpy: mgmt,
      grossJpy: gross,
    });
    rentJpy += rent;
    mgmtJpy += mgmt;
    grossJpy += gross;
  }

  return {
    asOf: asOf.toISOString().slice(0, 10),
    year: args.year,
    monthsInScope: currentMonths,
    properties,
    totals: { rentJpy, mgmtJpy, grossJpy },
    basis:
      "内容確認（property_units の家賃+管理費）×所有月数。財務19.1はNETのため家賃収入には使わない。当年は経過月まで。",
  };
}

export function isHouseholdReOtherIncome(category: string): boolean {
  const c = category || "";
  if (/19\.1/.test(c) && /家賃|不労所得/.test(c)) return false;
  return /19\.2|19\.4|19\.6|売却/.test(c);
}
