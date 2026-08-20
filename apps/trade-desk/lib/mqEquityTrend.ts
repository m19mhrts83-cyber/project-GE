/**
 * B/S 自己資本の年次推移（毎期プロット）
 */

import type { EntityFilter } from "./mqAggregate";
import {
  combineBs,
  normalizeBs,
  sumEquity,
  yearEndDate,
  type MqBsFields,
  type MqBsRow,
} from "./mqBs";

export type EquityTrendSource = "snapshot" | "cashflow_project" | "missing";

export type EquityTrendPoint = {
  year: number;
  asOf: string | null;
  equityMan: number | null;
  capitalMan: number | null;
  retainedMan: number | null;
  profitMan: number | null;
  source: EquityTrendSource;
  note: string | null;
};

function yearOfAsOf(asOf: string): number | null {
  const y = Number(String(asOf).slice(0, 4));
  return Number.isFinite(y) ? y : null;
}

/** その暦年（1/1〜12/31）のスナップだけ。前年の期末を翌年に流用しない */
function snapshotForYear(
  rows: MqBsRow[],
  line: string,
  entity: string,
  year: number
): MqBsRow | null {
  const start = `${year}-01-01`;
  const end = yearEndDate(String(year));
  const inYear = rows
    .filter(
      (r) =>
        r.business_line === line &&
        r.entity === entity &&
        String(r.as_of_date).slice(0, 10) >= start &&
        String(r.as_of_date).slice(0, 10) <= end
    )
    .sort((a, b) =>
      String(b.as_of_date).localeCompare(String(a.as_of_date))
    );
  return inYear[0] ?? null;
}

function fieldsFromSnap(snap: MqBsRow | null): {
  fields: MqBsFields | null;
  asOf: string | null;
  source: string | null;
} {
  if (!snap) return { fields: null, asOf: null, source: null };
  return {
    fields: normalizeBs(snap),
    asOf: String(snap.as_of_date).slice(0, 10),
    source: snap.source ?? null,
  };
}

/**
 * 投影B/Sの合算。スナップの combineBs と違い、片側 null は 0 として足す
 * （資金繰り未設定側の資本を合算から消さない）。
 */
export function combineProjectedEquityBs(
  a: MqBsFields | null,
  b: MqBsFields | null
): MqBsFields | null {
  if (!a && !b) return null;
  if (a && !b) return { ...a };
  if (!a && b) return { ...b };
  const keys = Object.keys(a!) as (keyof MqBsFields)[];
  const out = { ...a! };
  for (const k of keys) {
    const va = a![k];
    const vb = b![k];
    if (va == null && vb == null) out[k] = null;
    else out[k] = (va ?? 0) + (vb ?? 0);
  }
  return out;
}

export function yearsForEquityTrend(args: {
  bsRows: MqBsRow[];
  line: string;
  originYear?: number | null;
  throughYear: number;
}): number[] {
  const years = new Set<number>();
  const origin = args.originYear ?? args.throughYear;
  for (let y = origin; y <= args.throughYear; y++) years.add(y);
  for (const r of args.bsRows) {
    if (args.line !== "all" && r.business_line !== args.line) continue;
    const y = yearOfAsOf(String(r.as_of_date));
    if (y != null && y <= args.throughYear && y >= origin - 5) years.add(y);
  }
  return Array.from(years).sort((a, b) => a - b);
}

export function buildEquityTrend(args: {
  years: number[];
  bsRows: MqBsRow[];
  line: string;
  entity: EntityFilter;
  mqGByYear?: Record<number, number | null>;
  projectedByYear?: Record<number, MqBsFields | null | undefined>;
}): EquityTrendPoint[] {
  const {
    years,
    bsRows,
    line,
    entity,
    mqGByYear = {},
    projectedByYear = {},
  } = args;

  return years.map((year) => {
    const mqG = mqGByYear[year] ?? null;
    let fields: MqBsFields | null = null;
    let asOf: string | null = null;
    let source: EquityTrendSource = "missing";
    let note: string | null = null;

    if (line === "all") {
      note = "事業線「全体」のB/S推移は未対応";
    } else if (entity === "combined") {
      const pers = snapshotForYear(bsRows, line, "personal", year);
      const corp = snapshotForYear(bsRows, line, "corporate", year);
      const combined = combineBs(
        pers ? normalizeBs(pers) : null,
        corp ? normalizeBs(corp) : null
      );
      if (combined) {
        fields = combined;
        asOf = yearEndDate(String(year));
        source = "snapshot";
        if (!pers || !corp) note = "個人・法人の片方のみ";
      }
    } else {
      const snap = snapshotForYear(bsRows, line, entity, year);
      const got = fieldsFromSnap(snap);
      if (got.fields) {
        fields = got.fields;
        asOf = got.asOf;
        source = "snapshot";
      }
    }

    if (!fields && line !== "all" && projectedByYear[year]) {
      fields = projectedByYear[year] ?? null;
      asOf = yearEndDate(String(year));
      source = "cashflow_project";
      note = note ?? "資金繰り投影（B/Sスナップ未保存）";
    }

    if (!fields) {
      return {
        year,
        asOf: null,
        equityMan: null,
        capitalMan: null,
        retainedMan: null,
        profitMan: null,
        source: "missing",
        note: note ?? "B/Sなし",
      };
    }

    const equityMan = sumEquity(fields, mqG);
    return {
      year,
      asOf,
      equityMan,
      capitalMan: fields.capital,
      retainedMan: fields.retained_earnings,
      profitMan: fields.current_profit ?? mqG,
      source,
      note,
    };
  });
}

export function equityDelta(points: EquityTrendPoint[]): number | null {
  const nums = points
    .map((p) => p.equityMan)
    .filter((v): v is number => v != null);
  if (nums.length < 2) return null;
  return nums[nums.length - 1]! - nums[0]!;
}
