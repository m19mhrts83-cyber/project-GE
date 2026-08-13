/**
 * 買い進めプラン KPI — スピード感・個人／法人（価格合計より優先）
 *
 * yield_pct は Excel 由来で **小数**（0.25 = 25%）として格納されている。
 * 想定月家賃（粗）= 価格万円 × 10000 × yield ÷ 12（返済控除なし）。
 */

import { isBuyAction, isSaleAction, classifyBuyPlanAction } from "@/lib/buyPlanAction";

export const CF_GOAL_MONTH_YEN = 500_000;

export type BuyPlanEventLike = {
  action: string | null;
  entity: string | null;
  price_man: number | string | null;
  yield_pct: number | string | null;
  loan_man?: number | string | null;
  event_date: string | null;
  property_name?: string | null;
};

export type OwnerKind = "個人" | "法人" | "その他";

export function ownerKind(entity: string | null | undefined): OwnerKind {
  const e = (entity || "").trim();
  if (e.includes("法人")) return "法人";
  if (e.includes("個人")) return "個人";
  return "その他";
}

function num(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const x = typeof v === "number" ? v : Number(v);
  return Number.isFinite(x) ? x : null;
}

/** 利回り×価格 → 想定月家賃（粗・円）。yield は小数。 */
export function estMonthlyGrossRentYen(
  priceMan: number | string | null | undefined,
  yieldFrac: number | string | null | undefined
): number | null {
  const p = num(priceMan);
  const y = num(yieldFrac);
  if (p == null || y == null || p <= 0 || y <= 0) return null;
  return (p * 10_000 * y) / 12;
}

function parseDate(d: string | null | undefined): Date | null {
  if (!d) return null;
  const t = Date.parse(d.slice(0, 10));
  return Number.isFinite(t) ? new Date(t) : null;
}

export type PaceYearBucket = {
  year: number;
  buyPersonal: number;
  buyCorporate: number;
  cfPersonalYen: number;
  cfCorporateYen: number;
};

/** いま → 目標到達までの年次推移（何年後に何円か） */
export type PaceTrajectoryRow = {
  year: number;
  /** 0 = いま（当年起点） */
  yearsFromNow: number;
  label: string;
  /** その年にプランから積む想定月家賃（粗） */
  addYen: number;
  buys: number;
  /** いまのCF＋累積積み上げ */
  projectedCfYen: number;
  /** 目標までの残り（0以下なら到達） */
  remainingYen: number;
  reachedGoal: boolean;
};

export type BuyPlanPaceSummary = {
  goalYen: number;
  currentCfYen: number | null;
  gapYen: number | null;
  /** 今日以降の購入（利回り付き）件数 */
  futureBuysWithCf: number;
  futureBuysPersonal: number;
  futureBuysCorporate: number;
  /** 今日以降の想定月家賃積み上げ（粗）合計 */
  futureCfAddYen: number;
  futureCfPersonalYen: number;
  futureCfCorporateYen: number;
  financePersonal: number;
  financeCorporate: number;
  salePersonal: number;
  saleCorporate: number;
  /** プラン上の購入ペース（件/年） */
  buysPerYear: number | null;
  /** 想定CF積み上げの年平均（円/年） */
  cfAddPerYearYen: number | null;
  /** ギャップをプラン粗CFで埋める目安（何年後。0=今年中） */
  yearsToCloseGap: number | null;
  /** 累積でギャップ到達する年（YYYY） */
  reachYear: number | null;
  byYear: PaceYearBucket[];
  spanYears: number | null;
  /** いま＋各年末の想定CF推移 */
  trajectory: PaceTrajectoryRow[];
};

export function buildBuyPlanPaceSummary(
  events: BuyPlanEventLike[],
  opts: {
    asOf?: Date;
    currentCfYen?: number | null;
    goalYen?: number;
  } = {}
): BuyPlanPaceSummary {
  const asOf = opts.asOf ?? new Date();
  const asOfDay = new Date(
    asOf.getFullYear(),
    asOf.getMonth(),
    asOf.getDate()
  );
  const goalYen = opts.goalYen ?? CF_GOAL_MONTH_YEN;
  const currentCfYen =
    opts.currentCfYen == null || !Number.isFinite(opts.currentCfYen)
      ? null
      : Math.round(opts.currentCfYen);
  const gapYen =
    currentCfYen == null ? null : Math.max(0, Math.round(goalYen - currentCfYen));

  const byYearMap = new Map<number, PaceYearBucket>();
  let futureBuysWithCf = 0;
  let futureBuysPersonal = 0;
  let futureBuysCorporate = 0;
  let futureCfAddYen = 0;
  let futureCfPersonalYen = 0;
  let futureCfCorporateYen = 0;
  let financePersonal = 0;
  let financeCorporate = 0;
  let salePersonal = 0;
  let saleCorporate = 0;

  const ensure = (year: number): PaceYearBucket => {
    let b = byYearMap.get(year);
    if (!b) {
      b = {
        year,
        buyPersonal: 0,
        buyCorporate: 0,
        cfPersonalYen: 0,
        cfCorporateYen: 0,
      };
      byYearMap.set(year, b);
    }
    return b;
  };

  for (const e of events) {
    const own = ownerKind(e.entity);
    const kind = classifyBuyPlanAction(e.action);
    const dt = parseDate(e.event_date);
    const future = !dt || dt >= asOfDay;

    if (kind === "finance" && future) {
      if (own === "個人") financePersonal += 1;
      else if (own === "法人") financeCorporate += 1;
    }
    if (isSaleAction(e.action) && future) {
      if (own === "個人") salePersonal += 1;
      else if (own === "法人") saleCorporate += 1;
    }
    if (!isBuyAction(e.action)) continue;
    if (!future) continue;

    const cf = estMonthlyGrossRentYen(e.price_man, e.yield_pct);
    if (own === "個人") futureBuysPersonal += 1;
    else if (own === "法人") futureBuysCorporate += 1;

    if (cf == null) continue;
    futureBuysWithCf += 1;
    futureCfAddYen += cf;
    if (own === "個人") futureCfPersonalYen += cf;
    else if (own === "法人") futureCfCorporateYen += cf;

    if (dt) {
      const b = ensure(dt.getFullYear());
      if (own === "個人") {
        b.buyPersonal += 1;
        b.cfPersonalYen += cf;
      } else if (own === "法人") {
        b.buyCorporate += 1;
        b.cfCorporateYen += cf;
      }
    }
  }

  const byYear = [...byYearMap.values()].sort((a, b) => a.year - b.year);
  const spanYears =
    byYear.length === 0
      ? null
      : byYear[byYear.length - 1].year - byYear[0].year + 1;
  const futureBuyCountDated = byYear.reduce(
    (s, b) => s + b.buyPersonal + b.buyCorporate,
    0
  );
  const buysPerYear =
    spanYears && spanYears > 0
      ? Math.round((futureBuyCountDated / spanYears) * 10) / 10
      : null;
  const cfAddPerYearYen =
    spanYears && spanYears > 0
      ? Math.round(futureCfAddYen / spanYears)
      : null;

  let reachYear: number | null = null;
  let yearsToCloseGap: number | null = null;
  const asOfYear = asOfDay.getFullYear();
  const baseCf = currentCfYen ?? 0;

  const trajectory: PaceTrajectoryRow[] = [
    {
      year: asOfYear,
      yearsFromNow: 0,
      label: `いま（${asOfYear}）`,
      addYen: 0,
      buys: 0,
      projectedCfYen: Math.round(baseCf),
      remainingYen: Math.max(0, Math.round(goalYen - baseCf)),
      reachedGoal: baseCf + 1e-6 >= goalYen,
    },
  ];

  let cum = 0;
  let firstReachMarked = trajectory[0].reachedGoal;
  for (const b of byYear) {
    const add = b.cfPersonalYen + b.cfCorporateYen;
    cum += add;
    const projected = Math.round(baseCf + cum);
    const remaining = Math.max(0, Math.round(goalYen - projected));
    const reached = projected + 1e-6 >= goalYen;
    trajectory.push({
      year: b.year,
      yearsFromNow: Math.max(0, b.year - asOfYear),
      label: `${b.year}年末`,
      addYen: Math.round(add),
      buys: b.buyPersonal + b.buyCorporate,
      projectedCfYen: projected,
      remainingYen: remaining,
      reachedGoal: reached,
    });
    if (reached && !firstReachMarked) {
      reachYear = b.year;
      yearsToCloseGap = Math.max(0, b.year - asOfYear);
      firstReachMarked = true;
    }
  }
  if (gapYen != null && gapYen > 0) {
    if (reachYear == null && cfAddPerYearYen && cfAddPerYearYen > 0) {
      yearsToCloseGap = Math.ceil(gapYen / cfAddPerYearYen);
      reachYear = asOfYear + yearsToCloseGap;
    }
  } else if (gapYen === 0) {
    yearsToCloseGap = 0;
    reachYear = asOfYear;
  }

  return {
    goalYen,
    currentCfYen,
    gapYen,
    futureBuysWithCf,
    futureBuysPersonal,
    futureBuysCorporate,
    futureCfAddYen: Math.round(futureCfAddYen),
    futureCfPersonalYen: Math.round(futureCfPersonalYen),
    futureCfCorporateYen: Math.round(futureCfCorporateYen),
    financePersonal,
    financeCorporate,
    salePersonal,
    saleCorporate,
    buysPerYear,
    cfAddPerYearYen,
    yearsToCloseGap,
    reachYear,
    byYear,
    spanYears,
    trajectory,
  };
}
