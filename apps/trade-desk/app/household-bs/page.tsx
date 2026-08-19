import Shell from "@/components/Shell";
import HouseholdBsAdvicePanel from "@/components/HouseholdBsAdvicePanel";
import HouseholdBsPanel from "@/components/HouseholdBsPanel";
import HouseholdBsSummaryPanel from "@/components/HouseholdBsSummaryPanel";
import HouseholdBsTaxBandPanel from "@/components/HouseholdBsTaxBandPanel";
import HouseholdBsTrendPanel from "@/components/HouseholdBsTrendPanel";
import HouseholdBsYearNav from "@/components/HouseholdBsYearNav";
import {
  composeHouseholdBs,
  householdBsViewFromSnapshot,
  type HouseholdBsView,
} from "@/lib/householdBsCompose";
import {
  buildHouseholdBsSummary,
  buildHouseholdBsTrendRow,
  sortTrendRows,
  type HouseholdBsTrendRow,
} from "@/lib/householdBsInsights";
import { buildHouseholdTaxBand } from "@/lib/householdBsTaxBand";
import {
  MQ_FACT_SELECT,
  TAX_YEAR_METRICS_SELECT,
} from "@/lib/mqLeanSelect";
import type { TaxYearMetricRow } from "@/lib/taxInsights";
import { createClient } from "@/lib/supabase/server";
import type { MqFactRow } from "@/lib/mqAggregate";

export const dynamic = "force-dynamic";

function currentYear(): string {
  return String(new Date().getFullYear());
}

async function composeLive(
  supabase: Awaited<ReturnType<typeof createClient>>,
  year: string
): Promise<HouseholdBsView> {
  const yNum = Number(year);
  const [
    { data: portfolioSnaps },
    { data: securitiesSnaps },
    { data: liqAccounts },
    { data: liqSnaps },
    { data: mqRaw },
    { data: loans },
    { data: categoryYear },
    { data: debitMeta },
    { data: propertyUnits },
    { data: taxMetrics },
  ] = await Promise.all([
    supabase
      .from("portfolio_snapshots")
      .select("account_id, as_of, value_jpy, source")
      .order("as_of", { ascending: false })
      .limit(120),
    supabase
      .from("securities_holdings")
      .select("account_id, as_of, value_jpy, source")
      .order("as_of", { ascending: false })
      .limit(40),
    supabase.from("liquidity_accounts").select("id, name").eq("active", true),
    supabase
      .from("liquidity_snapshots")
      .select("account_id, as_of, balance_jpy")
      .order("as_of", { ascending: false })
      .limit(80),
    supabase
      .from("kurashift_mq_period_facts")
      .select(MQ_FACT_SELECT)
      .eq("scenario_kind", "actual")
      .eq("business_line", "realestate")
      .gte("period_month", `${year}-01-01`)
      .lte("period_month", `${year}-12-31`)
      .order("period_month", { ascending: false })
      .limit(80),
    supabase
      .from("kurashift_loan_tracker_loans")
      .select("id, name, balance_jpy, category_major, tags, payload"),
    supabase
      .from("kurashift_finance_category_year")
      .select("fiscal_year, category, income_jpy, expense_jpy")
      .eq("fiscal_year", yNum)
      .limit(200),
    supabase
      .from("sync_meta")
      .select("value")
      .eq("key", "card_debit_watch_summary")
      .maybeSingle(),
    supabase
      .from("property_units")
      .select("property_id, property_name, room, status, rent, note, payload"),
    supabase
      .from("kurashift_tax_year_metrics")
      .select(TAX_YEAR_METRICS_SELECT)
      .order("fiscal_year", { ascending: false })
      .limit(24),
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

  return composeHouseholdBs({
    year,
    grain: "year",
    portfolioSnaps: portfolioSnaps ?? [],
    securitiesSnaps: securitiesSnaps ?? [],
    liquiditySnaps: liqSnaps ?? [],
    liquidityLabels: liqLabels,
    mqFacts: (mqRaw ?? []) as MqFactRow[],
    loanTracker: loans ?? [],
    categoryYear: categoryYear ?? [],
    propertyUnits: (propertyUnits ?? []) as import("@/lib/roiAssets").PropertyUnitRow[],
    taxMetrics: (taxMetrics ?? []) as TaxYearMetricRow[],
    cardDebitAmountJpy,
    cardDebitDue,
  });
}

export default async function HouseholdBsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const year =
    typeof sp.year === "string" ? sp.year.slice(0, 4) : currentYear();
  const forceLive = sp.live === "1" || sp.live === "true";

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const currentYearNum = Number(currentYear());
  const trendFromYear = currentYearNum - 4;

  const [{ data: taxMetricsRaw }, { data: snapshotRow }, { data: snapshotRows }] =
    await Promise.all([
    supabase
      .from("kurashift_tax_year_metrics")
      .select(TAX_YEAR_METRICS_SELECT)
      .order("fiscal_year", { ascending: false })
      .limit(24),
    supabase
      .from("kurashift_household_bs_snapshots")
      .select("as_of_month, fiscal_year, payload, source, updated_at")
      .eq("fiscal_year", Number(year))
      .order("as_of_month", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("kurashift_household_bs_snapshots")
      .select("as_of_month, fiscal_year, payload, source, updated_at")
      .gte("fiscal_year", trendFromYear)
      .order("fiscal_year", { ascending: false })
      .order("as_of_month", { ascending: false })
      .limit(60),
  ]);

  const snapViewRaw =
    !forceLive && snapshotRow?.payload
      ? householdBsViewFromSnapshot(snapshotRow.payload)
      : null;
  const pastYear = Number(year) < Number(currentYear());
  const snapHasFiled = Boolean(
    snapViewRaw?.rows.some((r) => r.id === "re_rent_filed_personal")
  );
  const snapView =
    snapViewRaw &&
    (!pastYear || snapHasFiled) &&
    (snapViewRaw.reFlow ||
      snapViewRaw.rows.some(
        (r) => r.id === "re_rent_gross" || r.id === "re_rent_filed_personal"
      ))
      ? snapViewRaw
      : null;

  // スナップ優先: 表示はスナップ、助言もスナップから。live compose は未登録時のみ。
  const liveView = snapView ? null : await composeLive(supabase, year);
  const view: HouseholdBsView = snapView
    ? {
        ...snapView,
        snapshotAsOf: (snapshotRow!.as_of_month as string) ?? null,
        snapshotSource: (snapshotRow!.source as string) ?? "jarvis",
      }
    : {
        ...(liveView as HouseholdBsView),
        snapshotAsOf: null,
        snapshotSource: null,
      };

  const taxMetrics = (taxMetricsRaw ?? []) as TaxYearMetricRow[];
  const taxBand = buildHouseholdTaxBand({
    year,
    mqSlices: view.mqSlices,
    metrics: taxMetrics,
  });
  const latestByYear = new Map<
    number,
    {
      as_of_month: string | null;
      fiscal_year: number;
      payload: unknown;
      source: string | null;
    }
  >();
  for (const row of snapshotRows ?? []) {
    const fy = Number(row.fiscal_year);
    if (!latestByYear.has(fy)) {
      latestByYear.set(fy, {
        as_of_month: row.as_of_month as string | null,
        fiscal_year: fy,
        payload: row.payload,
        source: (row.source as string | null) ?? null,
      });
    }
  }
  const trendViewMap = new Map<number, HouseholdBsView>();
  for (const [fy, row] of latestByYear) {
    const parsed = householdBsViewFromSnapshot(row.payload);
    if (!parsed) continue;
    trendViewMap.set(fy, {
      ...parsed,
      snapshotAsOf: row.as_of_month,
      snapshotSource: row.source,
    });
  }
  const selectedYearNum = Number(view.year);
  if (!trendViewMap.has(selectedYearNum) || forceLive || selectedYearNum === currentYearNum) {
    trendViewMap.set(selectedYearNum, view);
  }
  const trendRows = sortTrendRows(
    [...trendViewMap.values()].map((v) => buildHouseholdBsTrendRow(v))
  );
  const currentTrendIdx = trendRows.findIndex((r) => r.year === selectedYearNum);
  const priorTrend: HouseholdBsTrendRow | null =
    currentTrendIdx > 0 ? trendRows[currentTrendIdx - 1] : null;
  const summary = buildHouseholdBsSummary(view, priorTrend);

  return (
    <Shell active="/household-bs" email={user?.email ?? null}>
      <p className="page-kicker">① · 家計B/S（キヨサキ4象限）</p>
      <h1>家計B/S</h1>
      <p className="sub">
        上段=損益の流れ（収入/支出）。下段=会計B/Sと同じ向き（左=資産、右=負債）。
        不動産家賃は内容確認（号室）×所有月。MQは参考のみ。/mq の事業B/Sとは混ぜません。
      </p>

      <HouseholdBsYearNav year={year} live={forceLive} />

      {view.snapshotAsOf ? (
        <p className="meta" style={{ marginTop: 8 }}>
          表示: {view.snapshotAsOf} スナップ（{view.snapshotSource ?? "jarvis"}
          ）。最新を見る場合は{" "}
          <a href={`/household-bs?year=${year}&live=1`}>live compose</a>。
        </p>
      ) : (
        <p className="meta" style={{ marginTop: 8 }}>
          表示: live compose（月次スナップ未登録）。MQ月次更新成功時に自動保存されます。
        </p>
      )}

      <HouseholdBsSummaryPanel summary={summary} />
      <HouseholdBsTrendPanel rows={trendRows} />
      <HouseholdBsPanel view={view} />
      <HouseholdBsTaxBandPanel band={taxBand} />
      <HouseholdBsAdvicePanel view={view} />

      <p className="meta" style={{ marginTop: 16 }}>
        詳細:{" "}
        <a href="/portfolio">資産</a> · <a href="/mq">MQ会計</a> ·{" "}
        <a href="/tax">確定申告</a>
      </p>
    </Shell>
  );
}
