import Shell from "@/components/Shell";
import LifeplanSheetsNav from "@/components/LifeplanSheetsNav";
import BudgetComposer from "@/components/BudgetComposer";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import {
  composeBudgetLines,
  yearTotals,
  type ActualYearCat,
  type BudgetRow,
} from "@/lib/budgetCompose";
import {
  annualNoticeCopy,
  isAnnualLifeplanWindow,
  parseLifeplanMode,
} from "@/lib/lifeplanNotices";
import {
  LIFEPLAN_ANNUAL_STEPS,
  LIFEPLAN_PUSH_ZAIM_JOB,
} from "@/lib/lifeplanSteps";

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
  const lookback = [planYear - 3, planYear - 2, planYear - 1];
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
      .limit(800),
  ]);

  const lines = composeBudgetLines(
    (budgetRows ?? []) as BudgetRow[],
    (actuals ?? []) as ActualYearCat[],
    planYear,
    fetchYears
  );
  const totals = yearTotals(lines, fetchYears);
  const fiscalPayload = { fiscal_year: planYear, trigger: mode };

  return (
    <Shell active="/lifeplan" email={user?.email ?? null}>
      <LifeplanSheetsNav current="budget" />
      <h1>予算編成</h1>
      <p className="sub">
        過去{lookback.length}年の数字を横に置き、{planYear}年の月別予算を確認します。基本は前年実績を見ながら翌年（または当年）を固める流れです。
      </p>

      {canonical ? (
        <p className="meta">
          正本 {canonical.label}（{canonical.as_of} / {canonical.version_key}）
        </p>
      ) : null}

      {isAnnualLifeplanWindow() && mode !== "annual" ? (
        <div className="notice">
          <strong>{notice.title}</strong>
          <p style={{ margin: "6px 0 10px" }}>{notice.body}</p>
          <a className="btn primary" href="/lifeplan/budget?mode=annual">
            年次更新を始める
          </a>
        </div>
      ) : null}

      {(mode === "annual" || mode === "re_purchase") && (
        <>
          <h2 style={{ fontSize: "1.05rem" }}>
            {mode === "re_purchase" ? "物件購入時の更新" : "年次更新"}（a〜d）
          </h2>
          <p className="meta">
            (a) 終了年度の実績 → (b) 当年度予算 → (c) 100歳計画へ反映 → (d) 将来予測の修正と評価。
            反映後の差は <a href="/lifeplan">100歳計画</a> の差分表示で見ます。
          </p>
          <div className="grid">
            {LIFEPLAN_ANNUAL_STEPS.map((s) => (
              <article className="card" key={s.job}>
                <header>
                  <span className="lvl">
                    ({s.key}) Step {s.n}
                  </span>
                  <strong>{s.title}</strong>
                </header>
                <p className="meta">{s.desc}</p>
                <EnqueueJobButton
                  jobType={s.job}
                  title={`${s.title}`}
                  payload={fiscalPayload}
                  label={
                    s.job === "lifeplan_update_century"
                      ? "記録のみをキューへ"
                      : "実行キューへ"
                  }
                />
              </article>
            ))}
          </div>
          <div className="card" style={{ margin: "12px 0 20px" }}>
            <header>
              <span className="lvl">任意</span>
              <strong>固めた予算を財務へ反映</strong>
            </header>
            <p className="meta">
              Numbers→CSV まで自動。Zaim 本番は確認付きです。
            </p>
            <EnqueueJobButton
              jobType={LIFEPLAN_PUSH_ZAIM_JOB}
              title="Zaim へ CSV まで"
              payload={{ ...fiscalPayload, confirm_apply: false }}
              label="CSVまでキューへ"
            />
            <EnqueueJobButton
              jobType={LIFEPLAN_PUSH_ZAIM_JOB}
              title="[本番Zaim] 月次予算反映"
              payload={{ ...fiscalPayload, confirm_apply: true }}
              label="Zaim本番反映（要確認）"
              requireConfirm
              confirmMessage="Zaim の月次予算を上書きします。よろしいですか？（本番反映）"
            />
          </div>
        </>
      )}

      {mode === "default" ? (
        <p className="meta">
          年次更新は{" "}
          <a href="/lifeplan/budget?mode=annual">こちら</a>
          。物件購入時は{" "}
          <a href="/lifeplan/budget?mode=re_purchase">計画更新</a>。
        </p>
      ) : null}

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
