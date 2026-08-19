#!/usr/bin/env npx tsx
/**
 * 家計B/S 月次スナップ保存（Phase C）
 *   cd apps/trade-desk && npx tsx scripts/householdBsSnapshot.ts [--year 2026] [--dry-run]
 */
import { createClient } from "@supabase/supabase-js";
import { composeHouseholdBs } from "../lib/householdBsCompose";
import type { MqFactRow } from "../lib/mqAggregate";

function env(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`${name} required`);
  return v;
}

async function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes("--dry-run");
  const yearArg = args.find((a) => /^\d{4}$/.test(a));
  const yearIdx = args.indexOf("--year");
  const year =
    yearArg ??
    (yearIdx >= 0 ? args[yearIdx + 1]?.slice(0, 4) : null) ??
    String(new Date().getFullYear());

  const sb = createClient(
    env("JARVIS_SUPABASE_URL"),
    env("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
  );

  const [
    { data: portfolioSnaps },
    { data: securitiesSnaps },
    { data: liqAccounts },
    { data: liqSnaps },
    { data: mqRaw },
    { data: loans },
    { data: categoryYear },
    { data: debitMeta },
  ] = await Promise.all([
    sb.from("portfolio_snapshots").select("account_id, as_of, value_jpy, source").order("as_of", { ascending: false }).limit(200),
    sb.from("securities_holdings").select("account_id, as_of, value_jpy, source").order("as_of", { ascending: false }).limit(40),
    sb.from("liquidity_accounts").select("id, name").eq("active", true),
    sb.from("liquidity_snapshots").select("account_id, as_of, balance_jpy").order("as_of", { ascending: false }).limit(80),
    sb.from("kurashift_mq_period_facts").select("id,business_line,entity,period_month,scenario_kind,plan_variant_id,q,pq,vq,f,f_annual,cash_in,cash_out,cash_end,depreciation_jpy").eq("scenario_kind", "actual").eq("business_line", "realestate").gte("period_month", `${year}-01-01`).lte("period_month", `${year}-12-31`).order("period_month", { ascending: false }).limit(80),
    sb.from("kurashift_loan_tracker_loans").select("id, name, balance_jpy, category_major, tags, payload"),
    sb.from("kurashift_finance_category_year").select("fiscal_year, category, income_jpy, expense_jpy").eq("fiscal_year", Number(year)).limit(200),
    sb.from("sync_meta").select("value").eq("key", "card_debit_watch_summary").maybeSingle(),
  ]);

  let cardDebitAmountJpy: number | null = null;
  let cardDebitDue: string | null = null;
  if (debitMeta?.value) {
    try {
      const brief = JSON.parse(debitMeta.value as string) as {
        olive_infinite?: { due_date?: string; amount_jpy?: number | null };
        top_alert?: { due_date?: string; amount_jpy?: number | null };
      };
      const top = brief.top_alert || {};
      const olive = brief.olive_infinite || {};
      cardDebitDue = String(top.due_date || olive.due_date || "") || null;
      const n = top.amount_jpy ?? olive.amount_jpy;
      if (typeof n === "number" && Number.isFinite(n)) cardDebitAmountJpy = n;
    } catch {
      /* ignore */
    }
  }

  const liqLabels = new Map(
    (liqAccounts ?? []).map((a) => [a.id as string, a.name as string])
  );

  const view = composeHouseholdBs({
    year,
    grain: "year",
    portfolioSnaps: portfolioSnaps ?? [],
    securitiesSnaps: securitiesSnaps ?? [],
    liquiditySnaps: liqSnaps ?? [],
    liquidityLabels: liqLabels,
    mqFacts: (mqRaw ?? []) as MqFactRow[],
    loanTracker: loans ?? [],
    categoryYear: categoryYear ?? [],
    cardDebitAmountJpy,
    cardDebitDue,
  });

  const now = new Date();
  const asOfMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const payload = {
    ...view,
    snapshotAsOf: asOfMonth,
    snapshotSource: "jarvis",
  };

  if (dryRun) {
    console.log(
      JSON.stringify({
        ok: true,
        dry_run: true,
        as_of_month: asOfMonth,
        fiscal_year: Number(year),
        asset_jpy: view.totals.assetJpy,
        liability_jpy: view.totals.liabilityJpy,
        rows: view.rows.length,
      })
    );
    return;
  }

  const { error } = await sb.from("kurashift_household_bs_snapshots").upsert(
    {
      as_of_month: asOfMonth,
      fiscal_year: Number(year),
      payload,
      source: "jarvis",
      note: "mq monthly runner",
      updated_at: new Date().toISOString(),
    },
    { onConflict: "as_of_month,fiscal_year" }
  );

  if (error) {
    console.error(JSON.stringify({ ok: false, error: error.message }));
    process.exit(1);
  }

  console.log(
    JSON.stringify({
      ok: true,
      as_of_month: asOfMonth,
      fiscal_year: Number(year),
      asset_jpy: view.totals.assetJpy,
      liability_jpy: view.totals.liabilityJpy,
    })
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
