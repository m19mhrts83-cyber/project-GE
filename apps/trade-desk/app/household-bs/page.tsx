import Shell from "@/components/Shell";
import HouseholdBsPanel from "@/components/HouseholdBsPanel";
import { composeHouseholdBs } from "@/lib/householdBsCompose";
import { createClient } from "@/lib/supabase/server";
import type { MqFactRow } from "@/lib/mqAggregate";

export const dynamic = "force-dynamic";

function currentYear(): string {
  return String(new Date().getFullYear());
}

export default async function HouseholdBsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const year =
    typeof sp.year === "string"
      ? sp.year.slice(0, 4)
      : currentYear();

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

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
    supabase
      .from("portfolio_snapshots")
      .select("account_id, as_of, value_jpy, source")
      .order("as_of", { ascending: false })
      .limit(200),
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
      .select("*")
      .eq("scenario_kind", "actual")
      .order("period_month", { ascending: false })
      .limit(500),
    supabase
      .from("kurashift_loan_tracker_loans")
      .select("id, name, balance_jpy, category_major, tags, payload"),
    supabase
      .from("kurashift_finance_category_year")
      .select("fiscal_year, category, income_jpy, expense_jpy")
      .eq("fiscal_year", Number(year))
      .limit(500),
    supabase
      .from("sync_meta")
      .select("value")
      .eq("key", "card_debit_watch_summary")
      .maybeSingle(),
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
    (liqAccounts ?? []).map((a) => [a.id, a.name as string])
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

  return (
    <Shell active="/household-bs" email={user?.email ?? null}>
      <p className="page-kicker">① · 家計B/S（キヨサキ4象限）</p>
      <h1>家計B/S</h1>
      <p className="sub">
        上段=収入/支出（フロー）、下段=資産/負債（ストック）。
        個人+法人はMQ合算がデフォルト。/mq の事業B/Sとは混ぜません。
      </p>

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">年度</span>
          <strong>{year}年</strong>
        </header>
        <div className="mq-slicer" style={{ marginTop: 8 }}>
          {[year, String(Number(year) - 1), String(Number(year) - 2)].map(
            (y) => (
              <a
                key={y}
                className={`btn${y === year ? " primary" : ""}`}
                href={`/household-bs?year=${y}`}
              >
                {y}
              </a>
            )
          )}
        </div>
      </div>

      <HouseholdBsPanel view={view} />

      <p className="meta" style={{ marginTop: 16 }}>
        詳細:{" "}
        <a href="/portfolio">資産</a> · <a href="/mq">MQ会計</a> ·{" "}
        <a href="/tax">確定申告</a>
      </p>
    </Shell>
  );
}
