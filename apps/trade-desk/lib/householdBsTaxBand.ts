/**
 * 家計B/S — 申告比較帯（Phase E）
 * 申告をCFの正にしない。主体ごとに別行。
 */

import type { MqSlice } from "./householdBsCompose";
import { yenToMan } from "./mqUnits";
import type { TaxYearMetricRow } from "./taxInsights";
import { yen } from "./taxInsights";

export type HouseholdTaxBandRow = {
  id: string;
  label: string;
  mqMan: number | null;
  filedMan: number | null;
  diffMan: number | null;
  scope: "personal" | "corporate";
  hint?: string;
};

export type HouseholdTaxBand = {
  year: string;
  rows: HouseholdTaxBandRow[];
  disclaimer: string;
};

const DISCLAIMER =
  "比較専用。MQ/Zaimを正に上書きしません。個人=暦年、法人=5月期。";

function diff(mq: number | null, filed: number | null): number | null {
  if (mq == null || filed == null) return null;
  return mq - filed;
}

export function buildHouseholdTaxBand(args: {
  year: string;
  mqSlices: MqSlice[];
  metrics: TaxYearMetricRow[];
}): HouseholdTaxBand {
  const yearNum = Number(args.year.slice(0, 4));
  const personalMq = args.mqSlices.find((s) => s.entity === "personal");
  const corpMq = args.mqSlices.find((s) => s.entity === "corporate");
  const personalTax = args.metrics.find(
    (m) => m.scope === "personal" && m.fiscal_year === yearNum
  );
  const corpTax = args.metrics.find(
    (m) => m.scope === "corporate" && m.fiscal_year === yearNum
  );

  const rows: HouseholdTaxBandRow[] = [];

  const pG = personalMq?.computed?.g ?? null;
  const pFiled = yen(personalTax?.payload?.re_income_jpy);
  const pFiledMan = pFiled != null ? yenToMan(pFiled) : null;
  rows.push({
    id: "personal_g",
    label: "個人 · 不動産G vs 申告所得",
    mqMan: pG,
    filedMan: pFiledMan,
    diffMan: diff(pG, pFiledMan),
    scope: "personal",
    hint: "暦年。収支内訳③",
  });

  const cG = corpMq?.computed?.g ?? null;
  const cFiled = yen(corpTax?.ordinary_income_jpy);
  const cFiledMan = cFiled != null ? yenToMan(cFiled) : null;
  rows.push({
    id: "corporate_g",
    label: "法人 · MQ G vs 経常利益",
    mqMan: cG,
    filedMan: cFiledMan,
    diffMan: diff(cG, cFiledMan),
    scope: "corporate",
    hint: "5月期。決算全体",
  });

  return { year: args.year, rows, disclaimer: DISCLAIMER };
}
