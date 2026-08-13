/**
 * 買い進め Excel 各版 → 年次の想定月次CF（粗）系列。
 * 購入で累積、売却は property_name 一致の直近購入CFを減算。
 */

import { isBuyAction, isSaleAction } from "@/lib/buyPlanAction";
import { estMonthlyGrossRentYen } from "@/lib/buyPlanPace";

export type BuyPlanCfEvent = {
  action: string | null;
  property_name?: string | null;
  price_man: number | string | null;
  yield_pct: number | string | null;
  event_date: string | null;
};

export type PlanVersionMeta = {
  versionKey: string;
  label: string;
  asOf: string | null;
};

/** 表示するメジャー版（正本方針の写し） */
export const BUY_PLAN_CHART_MAJOR_VERSIONS: PlanVersionMeta[] = [
  { versionKey: "240224", label: "計画 ver.1.0", asOf: "2024-02-24" },
  { versionKey: "250901", label: "計画 ver.2.2", asOf: "2025-09-01" },
  {
    versionKey: "251124",
    label: "計画 ver.3.1（現行）",
    asOf: "2025-11-24",
  },
];

export const CF_CHART_GOAL_YEN = 500_000;

export type YearCfPoint = {
  year: number;
  cfYen: number | null;
};

export type PlanCfSeries = {
  versionKey: string;
  label: string;
  asOf: string | null;
  byYear: YearCfPoint[];
};

function parseDate(d: string | null | undefined): Date | null {
  if (!d) return null;
  const t = Date.parse(d.slice(0, 10));
  return Number.isFinite(t) ? new Date(t) : null;
}

type Timed = {
  at: Date;
  kind: "buy" | "sale";
  name: string;
  cf: number;
};

function toTimed(events: BuyPlanCfEvent[]): Timed[] {
  const out: Timed[] = [];
  for (const e of events) {
    const dt = parseDate(e.event_date);
    if (!dt) continue;
    const name = (e.property_name || "").trim();
    if (isBuyAction(e.action)) {
      const cf = estMonthlyGrossRentYen(e.price_man, e.yield_pct);
      if (cf == null) continue;
      out.push({ at: dt, kind: "buy", name, cf });
    } else if (isSaleAction(e.action)) {
      out.push({ at: dt, kind: "sale", name, cf: 0 });
    }
  }
  out.sort((a, b) => a.at.getTime() - b.at.getTime());
  return out;
}

/** 年末時点の累積想定月次CF（粗） */
function cfAtYearEnd(timed: Timed[], year: number): number | null {
  const end = new Date(year + 1, 0, 1).getTime();
  const holdings = new Map<string, number[]>();
  let total = 0;
  let saw = false;
  for (const ev of timed) {
    if (ev.at.getTime() >= end) break;
    saw = true;
    if (ev.kind === "buy") {
      total += ev.cf;
      if (ev.name) {
        const stack = holdings.get(ev.name) || [];
        stack.push(ev.cf);
        holdings.set(ev.name, stack);
      }
    } else if (ev.name && holdings.has(ev.name)) {
      const stack = holdings.get(ev.name)!;
      const removed = stack.pop() ?? 0;
      total -= removed;
      if (stack.length === 0) holdings.delete(ev.name);
    }
  }
  return saw ? Math.round(total) : null;
}

export function buildPlanCfSeriesForVersion(
  meta: PlanVersionMeta,
  events: BuyPlanCfEvent[],
  years: number[]
): PlanCfSeries {
  const timed = toTimed(events);
  return {
    versionKey: meta.versionKey,
    label: meta.label,
    asOf: meta.asOf,
    byYear: years.map((year) => ({
      year,
      cfYen: cfAtYearEnd(timed, year),
    })),
  };
}

export function defaultChartYears(
  fromYear = 2011,
  toYear = new Date().getFullYear() + 8
): number[] {
  const out: number[] = [];
  for (let y = fromYear; y <= toYear; y++) out.push(y);
  return out;
}
