import { createClient } from "@/lib/supabase/server";
import {
  buildImportFactRow,
  prepareMqYearIngest,
} from "@/lib/mqIngestApply";
import type { FinanceTxnLite, MqAccountMapRow } from "@/lib/mqZaimMap";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const year = Number(body.year) || new Date().getFullYear();
  const force = Boolean(body.force);

  const [{ data: maps, error: mapErr }, { data: txns, error: txnErr }] =
    await Promise.all([
      supabase
        .from("kurashift_mq_account_map")
        .select("*")
        .eq("approved", true)
        .order("priority"),
      supabase
        .from("kurashift_finance_transactions")
        .select(
          "category,subcategory,entity,kind,txn_date,income_jpy,expense_jpy,from_account,to_account,description,memo"
        )
        .gte("txn_date", `${year}-01-01`)
        .lt("txn_date", `${year + 1}-01-01`)
        .limit(20000),
    ]);

  if (mapErr) {
    return NextResponse.json({ error: mapErr.message }, { status: 500 });
  }
  if (txnErr) {
    return NextResponse.json({ error: txnErr.message }, { status: 500 });
  }

  const { data: existing, error: exErr } = await supabase
    .from("kurashift_mq_period_facts")
    .select("id,business_line,entity,period_month,source,scenario_kind")
    .eq("scenario_kind", "actual")
    .gte("period_month", `${year}-01-01`)
    .lt("period_month", `${year + 1}-01-01`);

  if (exErr) {
    return NextResponse.json({ error: exErr.message }, { status: 500 });
  }

  const { result, plan } = prepareMqYearIngest(
    (txns ?? []) as FinanceTxnLite[],
    (maps ?? []) as MqAccountMapRow[],
    existing ?? [],
    { year, force }
  );

  let upserted = 0;
  for (const b of plan.toUpsert) {
    const row = buildImportFactRow(b, year);
    const { error } = await supabase.from("kurashift_mq_period_facts").upsert(row, {
      onConflict:
        "business_line,entity,period_month,scenario_kind,plan_variant_id",
    });
    if (error) {
      return NextResponse.json(
        {
          error: error.message,
          at: `${b.business_line}|${b.entity}|${b.period_month}`,
        },
        { status: 500 }
      );
    }
    upserted += 1;
  }

  let deletedStale = 0;
  if (plan.staleImportIds.length > 0) {
    const { error: delErr, count } = await supabase
      .from("kurashift_mq_period_facts")
      .delete({ count: "exact" })
      .in("id", plan.staleImportIds)
      .eq("source", "import");
    if (delErr) {
      return NextResponse.json({ error: delErr.message }, { status: 500 });
    }
    deletedStale = count ?? plan.staleImportIds.length;
  }

  return NextResponse.json({
    ok: true,
    year,
    upserted,
    deletedStale,
    skippedManual: plan.skippedManualMonths.length,
    skippedManualMonths: plan.skippedManualMonths,
    bucketCount: result.buckets.length,
    unmapped: result.unmapped.slice(0, 40),
    unmappedTotal: result.unmapped.length,
    loanMixedWarn: result.loanMixedWarn,
    heuristicRealestateCount: result.heuristicRealestateCount,
  });
}
