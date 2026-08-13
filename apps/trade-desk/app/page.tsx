import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import {
  annualNoticeCopy,
  isAnnualLifeplanWindow,
} from "@/lib/lifeplanNotices";
import { fmtRatePct, loadLiabilityRates } from "@/lib/liabilityRates";
import {
  computeNextAction,
  countStalledQueued,
  failedSources,
  parseWeeklySummary,
} from "@/lib/nextAction";
import {
  aggregateReCfFromCategoryYear,
  monthsElapsedInYear,
  type FinanceCategoryYearRow,
} from "@/lib/reFinanceYtd";

export const dynamic = "force-dynamic";

function mondayOfIsoDate(d = new Date()): string {
  // Asia/Tokyo の暦日で月曜週初を返す
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d);
  const y = Number(parts.find((p) => p.type === "year")?.value);
  const m = Number(parts.find((p) => p.type === "month")?.value);
  const day = Number(parts.find((p) => p.type === "day")?.value);
  const local = new Date(Date.UTC(y, m - 1, day));
  const dow = (local.getUTCDay() + 6) % 7;
  local.setUTCDate(local.getUTCDate() - dow);
  return local.toISOString().slice(0, 10);
}

export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const weekStart = mondayOfIsoDate();
  const taxYear = new Date().getFullYear() - 1;

  const [
    { data: accounts },
    { data: snaps },
    { data: themes },
    { data: consults },
    { data: annualDone },
    { data: planSnaps },
    { data: cashflow },
    { data: liqSnaps },
    { data: liqAccounts },
    { data: moneyOps },
    { data: syncMeta },
    { data: queuedJobs },
    { data: taxCase },
    { count: evidenceCount },
    { data: financeCats },
  ] = await Promise.all([
    supabase
      .from("portfolio_accounts")
      .select("id, name, kind")
      .eq("active", true),
    supabase
      .from("portfolio_snapshots")
      .select("account_id, as_of, value_jpy, source")
      .order("as_of", { ascending: false })
      .limit(80),
    supabase
      .from("kurashift_themes")
      .select(
        "id, title, hypothesis, amount_jpy, funding_path, status, created_at"
      )
      .in("status", ["draft", "consulting", "approved", "executing"])
      .order("created_at", { ascending: false })
      .limit(8),
    supabase
      .from("kurashift_consultations")
      .select("id, title, lane, status, created_at")
      .eq("status", "open")
      .order("created_at", { ascending: false })
      .limit(5),
    supabase
      .from("kurashift_jobs")
      .select("id")
      .eq("job_type", "lifeplan_push_zaim")
      .eq("status", "succeeded")
      .gte("finished_at", `${new Date().getFullYear()}-01-01`)
      .limit(1),
    supabase
      .from("kurashift_plan_snapshots")
      .select("label, fiscal_year, snapshot_at, metrics")
      .order("snapshot_at", { ascending: false })
      .limit(1),
    supabase
      .from("cashflow_week_summaries")
      .select(
        "week_start, income_jpy, expense_jpy, credit_spend_jpy, note, source"
      )
      .eq("week_start", weekStart)
      .maybeSingle(),
    supabase
      .from("liquidity_snapshots")
      .select("account_id, as_of, balance_jpy, source")
      .order("as_of", { ascending: false })
      .limit(80),
    supabase
      .from("liquidity_accounts")
      .select("id, name, kind, sort_order")
      .eq("active", true)
      .order("sort_order"),
    supabase
      .from("kurashift_money_ops")
      .select("id, title, kind, amount_jpy, status, from_account, to_account")
      .in("status", ["draft", "consulting", "approved", "executing"])
      .order("created_at", { ascending: false })
      .limit(5),
    supabase
      .from("sync_meta")
      .select("key, value, updated_at")
      .in("key", ["portfolio_weekly_at", "portfolio_weekly_summary"]),
    supabase
      .from("kurashift_jobs")
      .select("id, job_type, status, created_at")
      .eq("status", "queued")
      .order("created_at", { ascending: true })
      .limit(20),
    supabase
      .from("kurashift_tax_cases")
      .select("id, status, fiscal_year")
      .eq("scope", "personal")
      .eq("fiscal_year", taxYear)
      .maybeSingle(),
    supabase
      .from("kurashift_tax_evidence")
      .select("id", { count: "exact", head: true })
      .eq("fiscal_year", taxYear),
    supabase
      .from("kurashift_finance_category_year")
      .select("fiscal_year, category, income_jpy, expense_jpy, net_jpy")
      .eq("fiscal_year", new Date().getFullYear())
      .limit(200),
  ]);

  const metaMap = new Map((syncMeta ?? []).map((r) => [r.key, r]));
  const weeklySummary = parseWeeklySummary(
    metaMap.get("portfolio_weekly_summary")?.value ?? null
  );
  const weeklyAt = metaMap.get("portfolio_weekly_at")?.value ?? null;
  const fails = failedSources(weeklySummary);
  const stalled = countStalledQueued(queuedJobs ?? []);
  const month = new Date().getMonth() + 1;
  const taxSeason = month <= 3 || month === 12;
  const next = computeNextAction({
    summary: weeklySummary,
    themes: (themes ?? []).map((t) => ({
      id: t.id,
      status: t.status,
      title: t.title,
    })),
    stalledQueued: stalled,
    annualWindow: isAnnualLifeplanWindow(),
    annualDone: (annualDone?.length ?? 0) > 0,
    taxNeedsEvidence:
      taxSeason &&
      Boolean(taxCase) &&
      (evidenceCount ?? 0) === 0,
  });
  const partialWarn = weeklySummary?.last_full_ok === false;

  const nameById = new Map((accounts ?? []).map((a) => [a.id, a.name]));
  const kindById = new Map((accounts ?? []).map((a) => [a.id, a.kind]));
  const latestByAccount = new Map<
    string,
    { as_of: string; value_jpy: number; source: string | null }
  >();
  for (const row of snaps ?? []) {
    if (!latestByAccount.has(row.account_id)) {
      latestByAccount.set(row.account_id, {
        as_of: row.as_of,
        value_jpy: Number(row.value_jpy),
        source: row.source,
      });
    }
  }

  const isLoanAccount = (id: string) =>
    id.includes("policy_loan") ||
    (kindById.get(id) || "").includes("loan");

  const assetRows = [...latestByAccount.entries()]
    .filter(([id]) => !isLoanAccount(id))
    .map(([id, v]) => ({
      id,
      name: nameById.get(id) || id,
      ...v,
    }))
    .sort((a, b) => b.value_jpy - a.value_jpy);
  const total = assetRows.reduce((s, r) => s + r.value_jpy, 0);

  const loanRows = [...latestByAccount.entries()]
    .filter(([id]) => isLoanAccount(id))
    .map(([id, v]) => ({
      id,
      name: nameById.get(id) || id,
      ...v,
    }))
    .sort((a, b) => b.value_jpy - a.value_jpy);
  const loanTotal = loanRows.reduce((s, r) => s + r.value_jpy, 0);
  const liabilityRates = loadLiabilityRates();
  const activeLoanRates = loanRows
    .filter((r) => r.value_jpy > 0)
    .map((r) => {
      const rate = liabilityRates.insurance[r.id];
      return `${r.name}: ${fmtRatePct(rate?.rate_pct ?? null)}`;
    });

  const liqName = new Map((liqAccounts ?? []).map((a) => [a.id, a.name]));
  const latestLiq = new Map<
    string,
    { as_of: string; balance_jpy: number }
  >();
  for (const row of liqSnaps ?? []) {
    if (!latestLiq.has(row.account_id)) {
      latestLiq.set(row.account_id, {
        as_of: row.as_of,
        balance_jpy: Number(row.balance_jpy),
      });
    }
  }
  const bankRows = (liqAccounts ?? [])
    .filter((a) => a.kind === "bank" || a.kind === "cash")
    .map((a) => ({
      id: a.id,
      name: liqName.get(a.id) || a.name,
      snap: latestLiq.get(a.id),
    }))
    .filter((r) => r.snap)
    .sort(
      (a, b) => (b.snap?.balance_jpy ?? 0) - (a.snap?.balance_jpy ?? 0)
    );
  const bankTotal = bankRows.reduce(
    (s, r) => s + (r.snap?.balance_jpy ?? 0),
    0
  );

  const notice = annualNoticeCopy();
  const showAnnualNotice =
    isAnnualLifeplanWindow() && !(annualDone && annualDone.length > 0);

  const actionable = (themes ?? []).filter((t) =>
    ["draft", "consulting", "approved"].includes(t.status)
  );

  const plan = planSnaps?.[0];
  const planLabel = plan
    ? `${plan.label}${plan.fiscal_year ? ` (${plan.fiscal_year})` : ""}`
    : "未整備";
  const re19 = (
    plan?.metrics as
      | { re19?: { cf_jpy?: number; income_jpy?: number; expense_jpy?: number } }
      | null
  )?.re19;
  const CF_GOAL_MONTH = 500_000;
  const calendarYear = new Date().getFullYear();
  const { combined: combinedYtd } = aggregateReCfFromCategoryYear(
    (financeCats || []) as FinanceCategoryYearRow[],
    calendarYear
  );
  const monthsElapsed = monthsElapsedInYear();
  const combinedMonth =
    combinedYtd.categories.length > 0
      ? Math.round(combinedYtd.cf / monthsElapsed)
      : null;
  const cfAnnual = typeof re19?.cf_jpy === "number" ? re19.cf_jpy : null;
  const cfMonthLp = cfAnnual != null ? Math.round(cfAnnual / 12) : null;
  const cfMonth = combinedMonth ?? cfMonthLp;
  const cfGap = cfMonth != null ? CF_GOAL_MONTH - cfMonth : null;

  return (
    <Shell active="/" email={user?.email ?? null}>
      <p className="page-kicker">HOME · HQ</p>
      <h1>KURASHIFT</h1>
      <p className="sub">
        全体俯瞰。①資産・②ライフプラン／税・③不動産のサマリーと、その週の収支・銀行残高。詳細は各レーンへ。
      </p>

      <div
        className="card"
        style={{
          marginTop: 12,
          borderColor:
            next.level === "warn" ? "var(--danger, #b45309)" : undefined,
        }}
      >
        <header>
          <span className="lvl">いまやること</span>
          <strong>{next.label}</strong>
        </header>
        {next.href !== "/" ? (
          <p style={{ marginTop: 8 }}>
            <a className="btn primary" href={next.href}>
              開く →
            </a>
          </p>
        ) : null}
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">データの鮮度</span>
          <strong>
            {weeklyAt
              ? `最終週次メタ ${weeklyAt}`
              : "週次メタ未取得（Mac 週次後に表示）"}
          </strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          week={weeklySummary?.iso_week ?? "—"} · ok=
          {weeklySummary?.ok ?? "—"} · error={weeklySummary?.error ?? "—"} ·
          last_full_ok=
          {weeklySummary?.last_full_ok == null
            ? "—"
            : weeklySummary.last_full_ok
              ? "true"
              : "false"}
        </p>
        {fails.length > 0 ? (
          <ul className="meta" style={{ marginTop: 8, paddingLeft: 18 }}>
            {fails.map((f) => (
              <li key={f.id}>
                ⚠️ {f.label}
                {f.reason ? ` — ${f.reason}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="meta" style={{ marginTop: 8 }}>
            ✅ ソース別エラーなし（または未報告）
          </p>
        )}
        {stalled > 0 ? (
          <p className="meta" style={{ marginTop: 6 }}>
            ⚠️ キュー滞留 {stalled} 件（30分超）→ <a href="/jobs">ジョブ</a>
          </p>
        ) : null}
      </div>

      <div
        className="card"
        style={{
          marginTop: 12,
          background: "var(--card-soft)",
          borderStyle: "dashed",
        }}
      >
        <header>
          <span className="lvl">①-C</span>
          <strong>日常の短い回し方</strong>
        </header>
        <ol className="meta" style={{ margin: "8px 0 0", paddingLeft: 20 }}>
          <li>
            <strong>週次は自動</strong>
            …日曜 09:10＋Mac起動時／朝オープン。上の「データの鮮度」で失敗を確認
          </li>
          <li>
            <strong>いまやること</strong>
            …上の1行だけ押す（テーマ承認・失敗復旧など）
          </li>
          <li>
            <strong>大きな判断だけ承認</strong>
            …相談→内容確認→承認。ライフプランは年数回でよい
          </li>
        </ol>
      </div>

      {showAnnualNotice ? (
        <div className="notice">
          <strong>{notice.title}</strong>
          <p style={{ margin: "6px 0 10px" }}>{notice.body}</p>
          <a className="btn primary" href="/lifeplan?mode=annual">
            ライフプラン更新へ
          </a>
        </div>
      ) : null}

      <h2 style={{ marginTop: 8, fontSize: "1.05rem" }}>3本の柱</h2>
      <div className="grid">
        <article className="card">
          <header>
            <span className="lvl">① 資産運用</span>
            <strong>{fmtYen(total)}</strong>
          </header>
          <p className="meta">
            {assetRows.length}口座 · 週次スナップ（契約者貸付は含めない）
            {partialWarn ? " · ⚠️ 一部未取得の可能性" : ""}
          </p>
          <p className="meta">
            保険借入合計 {fmtYen(loanTotal)}
            {loanTotal > 0 ? "（頭金枠の把握用・負債）" : ""}
          </p>
          {activeLoanRates.length > 0 ? (
            <p className="meta">
              貸付利率: {activeLoanRates.join(" / ")}
              {" · "}
              <a href="/portfolio">詳細 →</a>
            </p>
          ) : null}
          <a href="/portfolio">資産の詳細 →</a>
        </article>
        <article className="card">
          <header>
            <span className="lvl">② 計画・税</span>
            <strong>{planLabel}</strong>
          </header>
          <p className="meta">
            {plan?.snapshot_at
              ? `直近プラン snap ${plan.snapshot_at}`
              : "ライフプラン／個人申告"}
          </p>
          <a href="/lifeplan">ライフプラン →</a>
          {" · "}
          <a href="/tax">個人申告 →</a>
        </article>
        <article className="card">
          <header>
            <span className="lvl">③ 不動産</span>
            <strong>
              {cfMonth != null
                ? `月次CF ${fmtYen(cfMonth)}`
                : "レーン"}
            </strong>
          </header>
          <p className="meta">
            目標 月50万
            {cfGap != null
              ? ` · ギャップ ${fmtYen(cfGap)}（個人＋法人・Zaim当年÷${monthsElapsed}ヶ月）`
              : " · スナップ待ち"}
          </p>
          <p className="meta">
            <a href="/realestate">不動産 →</a>
            {" · "}
            <a href="/realestate/deals">買い進め →</a>
          </p>
        </article>
        <article className="card">
          <header>
            <span className="lvl">進行中</span>
            <strong>
              {(themes?.length ?? 0) + (moneyOps?.length ?? 0)}
            </strong>
          </header>
          <p className="meta">
            テーマ {themes?.length ?? 0} · 資金移動 {moneyOps?.length ?? 0} ·
            相談 {consults?.length ?? 0}
          </p>
          <a href="/themes">テーマ →</a>
          {" · "}
          <a href="/money-ops">資金移動 →</a>
        </article>
      </div>

      <h2 style={{ marginTop: 28, fontSize: "1.05rem" }}>
        その週の家計・銀行
      </h2>
      <div className="grid">
        <article className="card">
          <header>
            <span className="lvl">週次収支</span>
            <strong>
              {cashflow?.week_start ?? weekStart}
            </strong>
          </header>
          <p className="meta">
            収入{" "}
            {cashflow?.income_jpy != null
              ? fmtYen(Number(cashflow.income_jpy))
              : "—"}{" "}
            · 支出{" "}
            {cashflow?.expense_jpy != null
              ? fmtYen(Number(cashflow.expense_jpy))
              : "—"}{" "}
            · クレカ{" "}
            {cashflow?.credit_spend_jpy != null
              ? fmtYen(Number(cashflow.credit_spend_jpy))
              : "—"}
          </p>
          {cashflow?.note ? (
            <p className="meta">{cashflow.note}</p>
          ) : (
            <p className="meta">週次ジョブ未実行なら資産ステータス更新で取得</p>
          )}
        </article>
        <article className="card">
          <header>
            <span className="lvl">銀行・現金</span>
            <strong>{fmtYen(bankTotal)}</strong>
          </header>
          <p className="meta">Zaim 残高スポット（トップ）</p>
          <ul className="meta" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {bankRows.slice(0, 6).map((r) => (
              <li key={r.id}>
                {r.name}: {fmtYen(r.snap!.balance_jpy)}
                <span className="meta"> ({r.snap!.as_of})</span>
              </li>
            ))}
            {bankRows.length === 0 ? <li>未取得</li> : null}
          </ul>
        </article>
      </div>
      <p style={{ marginTop: 10 }}>
        <span className="meta">
          週次は日曜 09:10 と Mac 起動／朝オープンで自動実行。下のボタンは気になったときの手動用。
        </span>
      </p>
      <EnqueueJobButton
        jobType="portfolio_weekly"
        title="資産＋流動性週次をキュー（手動）"
        payload={{ force: true }}
        label="週次を今すぐ更新（手動）"
      />

      <h2 style={{ marginTop: 28, fontSize: "1.1rem" }}>
        資産運用の次アクション
      </h2>
      <p className="meta" style={{ marginBottom: 12 }}>
        分析→提案→<strong>相談で内容確認</strong>→承認→実行。資金移動は{" "}
        <a href="/money-ops">資金移動オペ</a>（提案→承認→手順アシスト）。
      </p>
      <EnqueueJobButton
        jobType="theme_propose_from_status"
        title="資産ステータスから提案を生成"
        payload={{ limit: 6 }}
        label="ステータスから提案を生成"
      />

      <div className="card">
        {(themes ?? []).length === 0 ? (
          <p className="meta">
            まだテーマカードがありません。提案候補: {actionable.length}
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>状態</th>
                <th>テーマ</th>
                <th>金額</th>
                <th>経路</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(themes ?? []).map((t) => (
                <tr key={t.id}>
                  <td>{t.status}</td>
                  <td>
                    <a href={`/themes/${t.id}`}>
                      <strong>{t.title}</strong>
                    </a>
                    <div className="meta">{t.hypothesis}</div>
                  </td>
                  <td>
                    {t.amount_jpy != null ? fmtYen(Number(t.amount_jpy)) : "—"}
                  </td>
                  <td className="meta">{t.funding_path ?? "—"}</td>
                  <td>
                    {t.status === "consulting" ? (
                      <a
                        className="btn primary"
                        href={`/themes/${t.id}`}
                        style={{ fontSize: 12, padding: "4px 8px" }}
                      >
                        次へ: 相談確認→承認
                      </a>
                    ) : t.status === "draft" ? (
                      <a
                        className="btn primary"
                        href="/themes"
                        style={{ fontSize: 12, padding: "4px 8px" }}
                      >
                        次へ: 相談中へ
                      </a>
                    ) : t.status === "approved" || t.status === "executing" ? (
                      <a
                        className="btn primary"
                        href="/themes"
                        style={{ fontSize: 12, padding: "4px 8px" }}
                      >
                        次へ: 完走アシスト
                      </a>
                    ) : (
                      <EnqueueJobButton
                        jobType="theme_preview"
                        title={`preview ${t.title}`}
                        payload={{ theme_id: t.id }}
                        label="プレビュー"
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p style={{ marginTop: 12 }}>
          <a href="/themes">テーマ運用画面へ →</a>
        </p>
      </div>

      {(moneyOps ?? []).length > 0 ? (
        <div className="card" style={{ marginTop: 16 }}>
          <header>
            <span className="lvl">資金移動</span>
            <strong>{moneyOps!.length}</strong>
          </header>
          <table>
            <thead>
              <tr>
                <th>状態</th>
                <th>内容</th>
                <th>金額</th>
              </tr>
            </thead>
            <tbody>
              {moneyOps!.map((o) => (
                <tr key={o.id}>
                  <td>{o.status}</td>
                  <td>
                    <strong>{o.title}</strong>
                    <div className="meta">
                      {o.kind} · {o.from_account ?? "—"} → {o.to_account ?? "—"}
                    </div>
                  </td>
                  <td>
                    {o.amount_jpy != null ? fmtYen(Number(o.amount_jpy)) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ marginTop: 12 }}>
            <a href="/money-ops">資金移動オペへ →</a>
          </p>
        </div>
      ) : null}

      <h2 style={{ marginTop: 28, fontSize: "1.1rem" }}>
        他資産のステータス
      </h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>口座</th>
              <th>評価</th>
              <th>日付</th>
              <th>ソース</th>
            </tr>
          </thead>
          <tbody>
            {assetRows.length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  スナップショットがありません（週次を実行）
                </td>
              </tr>
            ) : (
              assetRows.slice(0, 10).map((r) => (
                <tr key={r.id}>
                  <td>{r.name}</td>
                  <td>{fmtYen(r.value_jpy)}</td>
                  <td className="meta">{r.as_of}</td>
                  <td className="meta">{r.source ?? "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <p className="meta" style={{ marginTop: 10 }}>
          詳細・内訳は <a href="/portfolio">資産</a>。
        </p>
      </div>
    </Shell>
  );
}
