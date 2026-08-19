/**
 * MQ 年度取込の DB I/O（PostgREST 1000件上限をページングで回避）
 */

import {
  buildImportFactRow,
  prepareMqYearIngest,
  type ExistingFactLite,
} from "./mqIngestApply";
import type { FinanceTxnLite, MqAccountMapRow } from "./mqZaimMap";

const PAGE = 1000;
const TXN_COLS =
  "id,category,subcategory,entity,kind,txn_date,income_jpy,expense_jpy,from_account,to_account,description,memo";

/** supabase-js client（server / service_role どちらでも可） */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Sb = any;

async function fetchAllPages<T>(
  pageQuery: (from: number, to: number) => Promise<{ data: T[] | null; error: { message: string } | null }>
): Promise<T[]> {
  const all: T[] = [];
  for (let from = 0; from < 200_000; from += PAGE) {
    const { data, error } = await pageQuery(from, from + PAGE - 1);
    if (error) throw new Error(error.message);
    const rows = data ?? [];
    all.push(...rows);
    if (rows.length < PAGE) break;
  }
  return all;
}

export async function fetchYearFinanceTxns(
  sb: Sb,
  year: number
): Promise<FinanceTxnLite[]> {
  return fetchAllPages((from, to) =>
    sb
      .from("kurashift_finance_transactions")
      .select(TXN_COLS)
      .gte("txn_date", `${year}-01-01`)
      .lt("txn_date", `${year + 1}-01-01`)
      .order("id", { ascending: true })
      .range(from, to)
  );
}

export async function fetchYearActualFacts(
  sb: Sb,
  year: number
): Promise<ExistingFactLite[]> {
  return fetchAllPages((from, to) =>
    sb
      .from("kurashift_mq_period_facts")
      .select("id,business_line,entity,period_month,source,scenario_kind")
      .eq("scenario_kind", "actual")
      .gte("period_month", `${year}-01-01`)
      .lt("period_month", `${year + 1}-01-01`)
      .order("id", { ascending: true })
      .range(from, to)
  );
}

export type MqReplaceRpcResult = {
  upserted: number;
  deleted_stale: number;
  skipped_manual: number;
};

export async function replaceYearImportRpc(
  sb: Sb,
  year: number,
  rows: ReturnType<typeof buildImportFactRow>[],
  force: boolean
): Promise<MqReplaceRpcResult> {
  const { data, error } = await sb.rpc("kurashift_mq_replace_year_import", {
    p_year: year,
    p_rows: rows,
    p_force: force,
  });
  if (error) throw new Error(error.message);
  const raw =
    typeof data === "string"
      ? (JSON.parse(data) as Record<string, unknown>)
      : ((data as Record<string, unknown> | null) ?? {});
  return {
    upserted: Number(raw.upserted ?? 0),
    deleted_stale: Number(raw.deleted_stale ?? 0),
    skipped_manual: Number(raw.skipped_manual ?? 0),
  };
}

export async function applyMqYearIngest(
  sb: Sb,
  maps: MqAccountMapRow[],
  opts: { year: number; force?: boolean; dryRun?: boolean }
) {
  const [txns, existing] = await Promise.all([
    fetchYearFinanceTxns(sb, opts.year),
    fetchYearActualFacts(sb, opts.year),
  ]);
  const { result, plan } = prepareMqYearIngest(txns, maps, existing, {
    year: opts.year,
    force: opts.force,
  });
  const importRows = plan.toUpsert.map((b) => buildImportFactRow(b, opts.year));
  const preview = {
    year: opts.year,
    txnCount: txns.length,
    upserted: plan.toUpsert.length,
    deletedStale: plan.staleImportIds.length,
    skippedManual: plan.skippedManualMonths.length,
    skippedManualMonths: plan.skippedManualMonths,
    bucketCount: result.buckets.length,
    unmappedTotal: result.unmapped.length,
    unmapped: result.unmapped.slice(0, 20),
    loanMixedWarn: result.loanMixedWarn,
    heuristicRealestateCount: result.heuristicRealestateCount,
    reasonCounts: result.reasonCounts,
  };
  if (opts.dryRun) {
    return { ...preview, dryRun: true as const, rpc: null };
  }
  if (txns.length === 0) {
    throw new Error(
      `${opts.year}年の kurashift_finance_transactions が0件のため置換しません`
    );
  }
  const rpc = await replaceYearImportRpc(
    sb,
    opts.year,
    importRows,
    Boolean(opts.force)
  );
  return {
    ...preview,
    dryRun: false as const,
    upserted: rpc.upserted,
    deletedStale: rpc.deleted_stale,
    skippedManual: rpc.skipped_manual,
    rpc,
  };
}
