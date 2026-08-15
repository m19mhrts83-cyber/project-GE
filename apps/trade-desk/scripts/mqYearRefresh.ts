/**
 * MQ 年度実績を Zaim TXN から再集計して置換（service_role）
 *
 * Usage:
 *   cd apps/trade-desk && set -a && source ../../.env.jarvis_private && set +a
 *   npx tsx scripts/mqYearRefresh.ts --year 2026
 *   npx tsx scripts/mqYearRefresh.ts --year 2026 --dry-run
 *   npx tsx scripts/mqYearRefresh.ts --year 2026 --force
 */
import { createClient } from "@supabase/supabase-js";
import {
  buildImportFactRow,
  prepareMqYearIngest,
} from "../lib/mqIngestApply";
import type { FinanceTxnLite, MqAccountMapRow } from "../lib/mqZaimMap";

function arg(name: string): string | null {
  const i = process.argv.indexOf(name);
  if (i < 0) return null;
  return process.argv[i + 1] ?? null;
}

async function main() {
  const year = Number(arg("--year")) || new Date().getFullYear();
  const dryRun = process.argv.includes("--dry-run");
  const force = process.argv.includes("--force");

  const url = process.env.JARVIS_SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key =
    process.env.JARVIS_SUPABASE_SERVICE_ROLE_KEY ||
    process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です");
  }
  const sb = createClient(url, key);

  const [{ data: maps, error: mapErr }, { data: txns, error: txnErr }] =
    await Promise.all([
      sb
        .from("kurashift_mq_account_map")
        .select("*")
        .eq("approved", true)
        .order("priority"),
      sb
        .from("kurashift_finance_transactions")
        .select(
          "category,subcategory,entity,kind,txn_date,income_jpy,expense_jpy,from_account,to_account,description,memo"
        )
        .gte("txn_date", `${year}-01-01`)
        .lt("txn_date", `${year + 1}-01-01`)
        .limit(50000),
    ]);
  if (mapErr) throw new Error(mapErr.message);
  if (txnErr) throw new Error(txnErr.message);

  const { data: existing, error: exErr } = await sb
    .from("kurashift_mq_period_facts")
    .select("id,business_line,entity,period_month,source,scenario_kind")
    .eq("scenario_kind", "actual")
    .gte("period_month", `${year}-01-01`)
    .lt("period_month", `${year + 1}-01-01`);
  if (exErr) throw new Error(exErr.message);

  const { result, plan } = prepareMqYearIngest(
    (txns ?? []) as FinanceTxnLite[],
    (maps ?? []) as MqAccountMapRow[],
    existing ?? [],
    { year, force }
  );

  const out = {
    ok: true,
    dryRun,
    year,
    txnCount: (txns ?? []).length,
    upserted: plan.toUpsert.length,
    deletedStale: plan.staleImportIds.length,
    skippedManual: plan.skippedManualMonths.length,
    skippedManualMonths: plan.skippedManualMonths,
    bucketCount: result.buckets.length,
    unmappedTotal: result.unmapped.length,
    unmapped: result.unmapped.slice(0, 20),
    loanMixedWarn: result.loanMixedWarn,
    heuristicRealestateCount: result.heuristicRealestateCount,
  };

  if (dryRun) {
    console.log(JSON.stringify(out, null, 2));
    return;
  }

  let upserted = 0;
  for (const b of plan.toUpsert) {
    const row = buildImportFactRow(b, year);
    const { error } = await sb.from("kurashift_mq_period_facts").upsert(row, {
      onConflict:
        "business_line,entity,period_month,scenario_kind,plan_variant_id",
    });
    if (error) throw new Error(`${error.message} at ${b.period_month}`);
    upserted += 1;
  }

  let deletedStale = 0;
  if (plan.staleImportIds.length > 0) {
    const { error: delErr } = await sb
      .from("kurashift_mq_period_facts")
      .delete()
      .in("id", plan.staleImportIds)
      .eq("source", "import");
    if (delErr) throw new Error(delErr.message);
    deletedStale = plan.staleImportIds.length;
  }

  console.log(
    JSON.stringify({ ...out, upserted, deletedStale, dryRun: false }, null, 2)
  );
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
