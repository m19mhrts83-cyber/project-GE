/**
 * MQ Zaim取込の適用（UI API / CLI 共用）
 * source=import を対象年度で置換。manual は保護（force 時のみ上書き）。
 */

import {
  aggregateZaimToMq,
  type FinanceTxnLite,
  type MqAccountMapRow,
  type MonthBucket,
} from "./mqZaimMap";

export type ExistingFactLite = {
  id?: string;
  business_line: string;
  entity: string;
  period_month: string;
  source: string | null;
  scenario_kind: string;
};

export type MqIngestApplyResult = {
  year: number;
  upserted: number;
  deletedStale: number;
  skippedManual: number;
  skippedManualMonths: string[];
  bucketCount: number;
  unmappedTotal: number;
  unmapped: AggregateUnmapped[];
  loanMixedWarn: boolean;
  heuristicRealestateCount: number;
  keptKeys: string[];
};

type AggregateUnmapped = {
  category: string;
  subcategory: string;
  entity: string;
  count: number;
  amount: number;
};

function factKey(line: string, entity: string, period: string): string {
  return `${line}|${entity}|${String(period).slice(0, 7)}`;
}

export function planMqIngestUpserts(
  buckets: MonthBucket[],
  existing: ExistingFactLite[],
  opts: { year: number; force?: boolean }
): {
  toUpsert: MonthBucket[];
  skippedManualMonths: string[];
  staleImportIds: string[];
  keptKeys: string[];
} {
  const manualKeys = new Set(
    existing
      .filter((r) => r.source === "manual")
      .map((r) => factKey(r.business_line, r.entity, r.period_month))
  );

  const toUpsert: MonthBucket[] = [];
  const skippedManualMonths: string[] = [];
  const keptKeys: string[] = [];

  for (const b of buckets) {
    const key = factKey(b.business_line, b.entity, b.period_month);
    if (!opts.force && manualKeys.has(key)) {
      skippedManualMonths.push(key);
      continue;
    }
    toUpsert.push(b);
    keptKeys.push(key);
  }

  const kept = new Set(keptKeys);
  // 手入力キーも「残す」対象（stale import 削除から除外）
  for (const k of manualKeys) kept.add(k);

  const staleImportIds: string[] = [];
  for (const r of existing) {
    if (r.scenario_kind !== "actual") continue;
    if (r.source !== "import") continue;
    const key = factKey(r.business_line, r.entity, r.period_month);
    if (!kept.has(key) && r.id) staleImportIds.push(r.id);
  }

  return { toUpsert, skippedManualMonths, staleImportIds, keptKeys };
}

export function buildImportFactRow(b: MonthBucket, year: number) {
  return {
    business_line: b.business_line,
    entity: b.entity,
    period_month: b.period_month,
    scenario_kind: "actual" as const,
    plan_variant_id: "",
    q: null as number | null,
    pq: Math.round(b.pq),
    vq: Math.round(b.vq),
    f: Math.round(b.f),
    f_annual: Math.round(b.f_annual),
    cash_in: Math.round(b.cash_in) || null,
    cash_out: Math.round(b.cash_out) || null,
    cash_end: null as number | null,
    note: `Zaim取込 ${year}（Qは未設定・手入力可）`,
    source: "import" as const,
    updated_at: new Date().toISOString(),
  };
}

/** 集計＋置換計画（DB書き込みなし） */
export function prepareMqYearIngest(
  txns: FinanceTxnLite[],
  maps: MqAccountMapRow[],
  existing: ExistingFactLite[],
  opts: { year: number; force?: boolean }
): {
  result: ReturnType<typeof aggregateZaimToMq>;
  plan: ReturnType<typeof planMqIngestUpserts>;
} {
  const result = aggregateZaimToMq(txns, maps, { year: opts.year });
  const plan = planMqIngestUpserts(result.buckets, existing, opts);
  return { result, plan };
}
