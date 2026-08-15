import { createClient } from "@/lib/supabase/server";
import {
  aggregateZaimToMq,
  type FinanceTxnLite,
  type MqAccountMapRow,
} from "@/lib/mqZaimMap";
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
          "category,subcategory,entity,kind,txn_date,income_jpy,expense_jpy"
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

  const result = aggregateZaimToMq(
    (txns ?? []) as FinanceTxnLite[],
    (maps ?? []) as MqAccountMapRow[],
    { year }
  );

  const { data: existing } = await supabase
    .from("kurashift_mq_period_facts")
    .select("id,business_line,entity,period_month,source,scenario_kind")
    .eq("scenario_kind", "actual")
    .gte("period_month", `${year}-01-01`)
    .lt("period_month", `${year + 1}-01-01`);

  const manualKeys = new Set(
    (existing ?? [])
      .filter((r) => r.source === "manual")
      .map(
        (r) =>
          `${r.business_line}|${r.entity}|${String(r.period_month).slice(0, 7)}`
      )
  );

  let upserted = 0;
  let skippedManual = 0;
  const skippedManualMonths: string[] = [];

  for (const b of result.buckets) {
    const key = `${b.business_line}|${b.entity}|${b.period_month.slice(0, 7)}`;
    if (!force && manualKeys.has(key)) {
      skippedManual += 1;
      skippedManualMonths.push(key);
      continue;
    }
    const row = {
      business_line: b.business_line,
      entity: b.entity,
      period_month: b.period_month,
      scenario_kind: "actual",
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
      source: "import",
      updated_at: new Date().toISOString(),
    };
    const { error } = await supabase
      .from("kurashift_mq_period_facts")
      .upsert(row, {
        onConflict:
          "business_line,entity,period_month,scenario_kind,plan_variant_id",
      });
    if (error) {
      return NextResponse.json(
        { error: error.message, at: key },
        { status: 500 }
      );
    }
    upserted += 1;
  }

  return NextResponse.json({
    ok: true,
    year,
    upserted,
    skippedManual,
    skippedManualMonths,
    bucketCount: result.buckets.length,
    unmapped: result.unmapped.slice(0, 40),
    unmappedTotal: result.unmapped.length,
    loanMixedWarn: result.loanMixedWarn,
  });
}
