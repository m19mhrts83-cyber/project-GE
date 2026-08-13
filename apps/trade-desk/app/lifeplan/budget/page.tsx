import Shell from "@/components/Shell";
import LifeplanSheetsNav from "@/components/LifeplanSheetsNav";
import BudgetComposer from "@/components/BudgetComposer";
import { createClient } from "@/lib/supabase/server";
import {
  budgetLookbackYears,
  composeBudgetLines,
  yearTotals,
  type ActualYearCat,
  type BudgetRow,
} from "@/lib/budgetCompose";
import {
  annualNoticeCopy,
  parseLifeplanMode,
} from "@/lib/lifeplanNotices";

export const dynamic = "force-dynamic";

export default async function LifeplanBudgetPage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string }>;
}) {
  const sp = await searchParams;
  const mode = parseLifeplanMode(sp.mode);
  const notice = annualNoticeCopy();
  const planYear = notice.planYear;
  const lookback = budgetLookbackYears(planYear);
  const fetchYears = [...lookback, planYear];

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: canonical } = await supabase
    .from("kurashift_lifeplan_versions")
    .select("id, version_key, as_of, label")
    .eq("is_canonical", true)
    .maybeSingle();

  const [{ data: budgetRows }, { data: actuals }] = await Promise.all([
    canonical
      ? supabase
          .from("kurashift_lifeplan_budget_rows")
          .select(
            "plan_year, month, numbers_category, category_key, amount_yen"
          )
          .eq("version_id", canonical.id)
          .in("plan_year", fetchYears)
          .limit(4000)
      : Promise.resolve({ data: [] as BudgetRow[] }),
    supabase
      .from("kurashift_finance_category_year")
      .select("fiscal_year, category, income_jpy, expense_jpy")
      .in("fiscal_year", fetchYears)
      .limit(2000),
  ]);

  const lines = composeBudgetLines(
    (budgetRows ?? []) as BudgetRow[],
    (actuals ?? []) as ActualYearCat[],
    planYear,
    lookback
  );
  const totals = yearTotals(lines, fetchYears);

  const actualYearsPresent = [
    ...new Set(
      ((actuals ?? []) as ActualYearCat[]).map((a) => a.fiscal_year)
    ),
  ].sort();

  return (
    <Shell active="/lifeplan" email={user?.email ?? null}>
      <LifeplanSheetsNav current="budget" />
      <h1>予算編成</h1>
      <p className="sub">
        {planYear}年の月別予算を確認するシートです。過去
        {lookback.join("・")}
        年の財務実績と、教育・不動産の内訳を横に置いて見ます。
      </p>

      {canonical ? (
        <p className="meta">
          正本 {canonical.label}（{canonical.as_of} / {canonical.version_key}）
          {actualYearsPresent.length
            ? ` · 財務実績あり: ${actualYearsPresent.join(", ")}`
            : " · 財務実績まだなし"}
        </p>
      ) : null}

      <div className="card notice" style={{ marginBottom: 16 }}>
        <header>
          <span className="lvl">いまの使い方</span>
          <strong>{planYear}年 月別予算の確認</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          年次更新の実行キュー（実績取込→生涯CF反映→Zaim反映）はまだ使いません。
          まず表の形と、2022・2023実績が入っているかを確認してください。
          {mode !== "default" ? (
            <>
              {" "}
              （mode={mode} でも実行ボタンは出していません）
            </>
          ) : null}
        </p>
      </div>

      {lines.length ? (
        <BudgetComposer
          planYear={planYear}
          lookbackYears={lookback}
          lines={lines}
          totals={totals}
        />
      ) : (
        <div className="card">
          <p className="meta" style={{ margin: 0 }}>
            月別予算がまだ取り込まれていません。履歴取り込み後に再読み込みしてください。
          </p>
        </div>
      )}
    </Shell>
  );
}
