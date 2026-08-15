/**
 * MQ会計評価 — 集約（実績=月次＋年額÷12 / 計画=年次）
 */

import {
  computeMq,
  monthlyAllocatedF,
  sumMqInputs,
  yearlyFFromMonthlyRows,
  type MqComputed,
  type MqInput,
} from "./mqEquations";

export type MqFactRow = {
  id: string;
  business_line: string;
  entity: string;
  period_month: string;
  scenario_kind: string;
  plan_variant_id?: string | null;
  q: number | string | null;
  pq: number | string;
  vq: number | string;
  f: number | string;
  f_annual?: number | string | null;
  cash_in: number | string | null;
  cash_out: number | string | null;
  cash_end: number | string | null;
  depreciation_jpy: number | string | null;
};

export type LineFilter = "realestate" | "ai" | "all";
export type EntityFilter = "personal" | "corporate" | "combined";
export type GrainFilter = "month" | "year";
/** actual_actual | actual_plan | plan_plan */
export type CompareMode = "aa" | "ap" | "pp";

function n(v: number | string | null | undefined): number {
  if (v == null || v === "") return 0;
  const x = Number(v);
  return Number.isFinite(x) ? x : 0;
}

function nNull(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
}

export function monthKey(periodMonth: string): string {
  return String(periodMonth).slice(0, 7);
}

export function yearKey(periodMonth: string): string {
  return String(periodMonth).slice(0, 4);
}

export function filterFactsMonth(
  rows: MqFactRow[],
  line: LineFilter,
  entity: EntityFilter,
  month: string
): MqFactRow[] {
  const m = month.slice(0, 7);
  return rows.filter((r) => {
    if (r.scenario_kind !== "actual") return false;
    if (monthKey(r.period_month) !== m) return false;
    if (line !== "all" && r.business_line !== line) return false;
    if (entity !== "combined" && r.entity !== entity) return false;
    return true;
  });
}

/** 暦年の実績月次行 */
export function filterFactsYearActual(
  rows: MqFactRow[],
  line: LineFilter,
  entity: EntityFilter,
  year: string
): MqFactRow[] {
  const y = year.slice(0, 4);
  return rows.filter((r) => {
    if (r.scenario_kind !== "actual") return false;
    if (yearKey(r.period_month) !== y) return false;
    if (line !== "all" && r.business_line !== line) return false;
    if (entity !== "combined" && r.entity !== entity) return false;
    return true;
  });
}

function cashAgg(rows: MqFactRow[]) {
  let cashIn: number | null = null;
  let cashOut: number | null = null;
  let cashEnd: number | null = null;
  let depreciation: number | null = null;
  for (const r of rows) {
    const ci = nNull(r.cash_in);
    const co = nNull(r.cash_out);
    const ce = nNull(r.cash_end);
    const d = nNull(r.depreciation_jpy);
    if (ci != null) cashIn = (cashIn ?? 0) + ci;
    if (co != null) cashOut = (cashOut ?? 0) + co;
    if (ce != null) cashEnd = (cashEnd ?? 0) + ce;
    if (d != null) depreciation = (depreciation ?? 0) + d;
  }
  return { cashIn, cashOut, cashEnd, depreciation };
}

function byLineBreakdown(rows: MqFactRow[], mode: "month" | "year") {
  const map = new Map<string, MqFactRow[]>();
  for (const r of rows) {
    const list = map.get(r.business_line) || [];
    list.push(r);
    map.set(r.business_line, list);
  }
  // includeByLine:false — 再帰防止（事業線ごとの集計では byLine を作らない）
  return Array.from(map.entries())
    .map(([line, list]) => ({
      line,
      computed: aggregateRows(list, mode, { includeByLine: false }).computed!,
    }))
    .filter((x) => x.computed);
}

export function aggregateRows(
  rows: MqFactRow[],
  mode: "month" | "year",
  opts?: { includeByLine?: boolean }
): {
  input: MqInput;
  computed: MqComputed | null;
  cashIn: number | null;
  cashOut: number | null;
  cashEnd: number | null;
  depreciation: number | null;
  byLine: { line: string; computed: MqComputed }[];
  fMonthlyPart: number;
  fAnnualAllocated: number;
} {
  const includeByLine = opts?.includeByLine !== false;
  if (rows.length === 0) {
    return {
      input: { pq: 0, vq: 0, f: 0, q: null },
      computed: null,
      cashIn: null,
      cashOut: null,
      cashEnd: null,
      depreciation: null,
      byLine: [],
      fMonthlyPart: 0,
      fAnnualAllocated: 0,
    };
  }

  let pq = 0;
  let vq = 0;
  let qSum = 0;
  let qAny = false;
  for (const r of rows) {
    pq += n(r.pq);
    vq += n(r.vq);
    const q = nNull(r.q);
    if (q != null && q > 0) {
      qSum += q;
      qAny = true;
    }
  }

  let fEffective: number;
  let fMonthlyPart: number;
  let fAnnualAllocated: number;
  if (mode === "month") {
    fMonthlyPart = rows.reduce((s, r) => s + n(r.f), 0);
    const fAnnual = rows.reduce((s, r) => s + n(r.f_annual), 0);
    fAnnualAllocated = fAnnual / 12;
    fEffective = monthlyAllocatedF(fMonthlyPart, fAnnual);
  } else {
    fMonthlyPart = rows.reduce((s, r) => s + n(r.f), 0);
    fAnnualAllocated = yearlyFFromMonthlyRows(
      rows.map((r) => ({ f: 0, f_annual: n(r.f_annual) }))
    );
    fEffective = yearlyFFromMonthlyRows(
      rows.map((r) => ({ f: n(r.f), f_annual: n(r.f_annual) }))
    );
  }

  const input: MqInput = {
    pq,
    vq,
    f: fEffective,
    q: qAny ? qSum : null,
  };
  const cash = cashAgg(rows);
  return {
    input,
    computed: computeMq(input),
    ...cash,
    byLine: includeByLine ? byLineBreakdown(rows, mode) : [],
    fMonthlyPart,
    fAnnualAllocated,
  };
}

export function availableMonths(rows: MqFactRow[]): string[] {
  const s = new Set(
    rows.filter((r) => r.scenario_kind === "actual").map((r) => monthKey(r.period_month))
  );
  return Array.from(s).sort().reverse();
}

export function availableYears(rows: MqFactRow[]): string[] {
  const s = new Set(
    rows
      .filter((r) => r.scenario_kind === "actual" || r.scenario_kind === "plan")
      .map((r) => yearKey(r.period_month))
  );
  return Array.from(s).sort().reverse();
}

/** 年次計画行（period は当該年の1月） */
export function filterPlans(
  rows: MqFactRow[],
  line: LineFilter,
  entity: EntityFilter,
  year: string,
  variantId?: string | null
): MqFactRow[] {
  const y = year.slice(0, 4);
  return rows.filter((r) => {
    if (r.scenario_kind !== "plan") return false;
    if (yearKey(r.period_month) !== y) return false;
    if (line !== "all" && r.business_line !== line) return false;
    if (entity !== "combined" && r.entity !== entity) return false;
    if (variantId != null && variantId !== "" && (r.plan_variant_id || "") !== variantId) {
      return false;
    }
    return true;
  });
}

export function listPlanVariants(rows: MqFactRow[], year?: string): string[] {
  const s = new Set<string>();
  for (const r of rows) {
    if (r.scenario_kind !== "plan") continue;
    if (year && yearKey(r.period_month) !== year.slice(0, 4)) continue;
    const id = (r.plan_variant_id || "").trim();
    if (id) s.add(id);
  }
  return Array.from(s).sort();
}

/**
 * 年次計画の集約。計画行の pq/vq/f は年額。f_annual があれば加算。
 */
export function aggregatePlanAnnual(rows: MqFactRow[]) {
  if (rows.length === 0) {
    return {
      input: { pq: 0, vq: 0, f: 0, q: null } as MqInput,
      computed: null as MqComputed | null,
      cashIn: null as number | null,
      cashOut: null as number | null,
      cashEnd: null as number | null,
      depreciation: null as number | null,
      byLine: [] as { line: string; computed: MqComputed }[],
      fMonthlyPart: 0,
      fAnnualAllocated: 0,
    };
  }
  let pq = 0;
  let vq = 0;
  let f = 0;
  let qSum = 0;
  let qAny = false;
  for (const r of rows) {
    pq += n(r.pq);
    vq += n(r.vq);
    f += n(r.f) + n(r.f_annual);
    const q = nNull(r.q);
    if (q != null && q > 0) {
      qSum += q;
      qAny = true;
    }
  }
  const input: MqInput = { pq, vq, f, q: qAny ? qSum : null };
  return {
    input,
    computed: computeMq(input),
    cashIn: null,
    cashOut: null,
    cashEnd: null,
    depreciation: null,
    byLine: [],
    fMonthlyPart: 0,
    fAnnualAllocated: f,
  };
}

/** 年次計画を月次比較用に÷12（空室チューニング用） */
export function scaleAnnualComputedToMonth(c: MqComputed): MqComputed {
  return computeMq({
    pq: c.pq / 12,
    vq: c.vq / 12,
    f: c.f / 12,
    q: c.q != null ? c.q / 12 : null,
  });
}

export function lineLabel(line: string): string {
  if (line === "realestate") return "不動産";
  if (line === "ai") return "AI";
  if (line === "all") return "全体";
  return line;
}

export function entityLabel(entity: string): string {
  if (entity === "personal") return "個人";
  if (entity === "corporate") return "法人";
  if (entity === "combined") return "合算";
  return entity;
}

/** 比較バー用 */
export function metricBars(c: MqComputed | null): { label: string; value: number }[] {
  if (!c) return [];
  return [
    { label: "PQ", value: c.pq },
    { label: "VQ", value: c.vq },
    { label: "MQ", value: c.mq },
    { label: "F", value: c.f },
    { label: "G", value: c.g },
  ];
}

// re-export for callers that used old name
export function filterFacts(
  rows: MqFactRow[],
  line: LineFilter,
  entity: EntityFilter,
  month: string
): MqFactRow[] {
  return filterFactsMonth(rows, line, entity, month);
}

export function aggregateFacts(rows: MqFactRow[]) {
  return aggregateRows(rows, "month");
}

export { sumMqInputs };
