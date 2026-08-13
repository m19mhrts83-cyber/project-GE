import Shell from "@/components/Shell";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
import { createClient } from "@/lib/supabase/server";
import { fmtYen, fmtYenSigned } from "@/lib/format";
import { loadLiabilityRates } from "@/lib/liabilityRates";
import {
  completeMonthsElapsed,
  tokyoYmd,
  aggregateReCfFromCategoryYear,
  type FinanceCategoryYearRow,
} from "@/lib/reFinanceYtd";
import {
  SPECIAL_LABEL,
  composeReSteadyBoard,
} from "@/lib/reSteadyCf";
import type { PropertyUnitRow } from "@/lib/roiAssets";
import { buildBRate4Rows, fmtPct } from "@/lib/bRate4";
import { dscrLabel, fmtDscr, simpleDscr } from "@/lib/reDscr";
import { RE_PROPERTY_MASTER } from "@/lib/rePropertyMaster";
import { buildPlanProgress } from "@/lib/rePlanProgress";

export const dynamic = "force-dynamic";

export default async function RealEstatePage({
  searchParams,
}: {
  searchParams: Promise<{ scope?: string }>;
}) {
  const sp = await searchParams;
  const scopeRaw = (sp.scope || "combined").toLowerCase();
  const scope =
    scopeRaw === "personal" || scopeRaw === "corporate"
      ? scopeRaw
      : "combined";

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { year: calendarYear } = tokyoYmd();
  const actualsYear = calendarYear - 1;
  const throughMonth = completeMonthsElapsed();
  const liabilityRates = loadLiabilityRates();

  const { data: yearSnap } = await supabase
    .from("kurashift_plan_snapshots")
    .select("fiscal_year, snapshot_at, metrics, label")
    .eq("fiscal_year", actualsYear)
    .order("snapshot_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  let latestSnap = yearSnap;
  if (!latestSnap) {
    const { data: anySnap } = await supabase
      .from("kurashift_plan_snapshots")
      .select("fiscal_year, snapshot_at, metrics, label")
      .order("snapshot_at", { ascending: false })
      .limit(8);
    latestSnap =
      (anySnap || []).find((s) => {
        const m = s.metrics as { re19?: unknown } | null;
        return Boolean(m?.re19);
      }) ?? null;
  }

  const re19 = (latestSnap?.metrics as { re19?: { income_jpy?: number; expense_jpy?: number; cf_jpy?: number } } | null)
    ?.re19;

  const [
    { data: unitRows },
    { data: buyPlan },
    { data: dealRows },
    { data: reTxns },
    { data: loanRows },
    { data: catYear },
  ] = await Promise.all([
      supabase
        .from("property_units")
        .select("property_id, property_name, room, status, rent, note, payload"),
      supabase
        .from("kurashift_buy_plan_versions")
        .select("version_key, label, as_of, metadata")
        .eq("is_canonical", true)
        .maybeSingle(),
      supabase.from("kurashift_re_deals").select("status"),
      supabase
        .from("kurashift_finance_transactions")
        .select("category, subcategory, txn_date, income_jpy, expense_jpy, to_account")
        .eq("fiscal_year", calendarYear)
        .or("category.ilike.%19%,category.ilike.%賃貸%,category.ilike.%家賃%")
        .limit(4000),
      supabase
        .from("kurashift_loan_tracker_loans")
        .select(
          "id, name, lender, rate_pct, balance_jpy, monthly_payment_jpy, tags, payload"
        )
        .limit(80),
      supabase
        .from("kurashift_finance_category_year")
        .select("fiscal_year, category, income_jpy, expense_jpy, net_jpy")
        .eq("fiscal_year", calendarYear)
        .limit(500),
    ]);

  const bRate4All = buildBRate4Rows(loanRows || []);
  const ownerOf = (propertyId: string) =>
    RE_PROPERTY_MASTER.find((p) => p.id === propertyId)?.owner || "";
  const bRate4 = bRate4All.filter((r) => {
    if (scope === "combined") return true;
    const o = ownerOf(r.propertyId);
    if (scope === "personal") return o === "個人";
    if (scope === "corporate") return o === "法人";
    return true;
  });

  const rentByProp = new Map<string, number>();
  for (const u of unitRows || []) {
    const pid = String(u.property_id || "");
    if (!pid) continue;
    if (scope !== "combined") {
      const o = ownerOf(pid);
      if (scope === "personal" && o !== "個人") continue;
      if (scope === "corporate" && o !== "法人") continue;
    }
    rentByProp.set(pid, (rentByProp.get(pid) || 0) + (Number(u.rent) || 0));
  }
  const portfolioRent = [...rentByProp.values()].reduce((a, b) => a + b, 0);
  const portfolioPay = bRate4.reduce(
    (s, r) => s + (r.monthlyPaymentJpy || 0),
    0
  );
  const portfolioDscr = simpleDscr(portfolioRent, portfolioPay);

  const loanTrackerPayMonth = (loanRows || []).reduce((s, l) => {
    const v = l.monthly_payment_jpy == null ? 0 : Number(l.monthly_payment_jpy);
    return s + (Number.isFinite(v) ? v : 0);
  }, 0);

  const ytdCf = aggregateReCfFromCategoryYear(
    (catYear || []) as FinanceCategoryYearRow[],
    calendarYear
  );
  const ytdBucket =
    scope === "personal"
      ? ytdCf.personal
      : scope === "corporate"
        ? ytdCf.corporate
        : ytdCf.combined;

  const unitCount = unitRows?.length ?? 0;
  const reBoard = composeReSteadyBoard(
    reTxns ?? [],
    (unitRows ?? []) as PropertyUnitRow[],
    calendarYear,
    throughMonth
  );

  const funnelOrder = [
    "info",
    "viewing",
    "offer",
    "loan",
    "purchased",
    "passed",
  ] as const;
  const funnelCounts: Record<string, number> = {};
  for (const s of funnelOrder) funnelCounts[s] = 0;
  for (const d of dealRows || []) {
    const st = d.status as string;
    funnelCounts[st] = (funnelCounts[st] || 0) + 1;
  }

  const CF_GOAL_MONTH = 500_000;
  const cfAnnual = typeof re19?.cf_jpy === "number" ? re19.cf_jpy : null;
  const assumedGap = CF_GOAL_MONTH - reBoard.assumedCfMonth;

  /** 合算: 目標50万。個人／法人: そのスコープの満室想定CFを計画月次とする */
  const planMonthForBar =
    scope === "combined"
      ? CF_GOAL_MONTH
      : Math.max(0, Math.round(reBoard.assumedCfMonth));
  const planProg = buildPlanProgress({
    planMonthYen: planMonthForBar,
    actualYtdYen: ytdBucket.cf,
    months: throughMonth,
  });
  const assumedProg = buildPlanProgress({
    planMonthYen: Math.max(0, Math.round(reBoard.assumedCfMonth)),
    actualYtdYen: ytdBucket.cf,
    months: throughMonth,
  });
  const barPct = Math.min(100, Math.max(0, planProg.pct ?? 0));

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="a" />
      <h1>不動産賃貸経営 · 運用・進捗</h1>
      <p className="sub">
        ③-A: 今持っている資産のCF・返済余裕・計画ギャップ。目標は{" "}
        <strong>CF 月50万円</strong>（個人＋法人合算）。
        買い進めの長期年表は{" "}
        <a href="/realestate/buy-plan">レーンB</a>。
      </p>

      <p className="meta" style={{ marginBottom: 12 }}>
        名義:{" "}
        <a href="/realestate?scope=combined">
          {scope === "combined" ? <strong>合算</strong> : "合算"}
        </a>
        {" · "}
        <a href="/realestate?scope=personal">
          {scope === "personal" ? <strong>個人</strong> : "個人"}
        </a>
        {" · "}
        <a href="/realestate?scope=corporate">
          {scope === "corporate" ? <strong>法人</strong> : "法人"}
        </a>
      </p>

      <div className="card notice">
        <header>
          <span className="lvl">Portfolio KPI</span>
          <strong>レントロール × 返済 × DSCR（簡易）</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          DSCR 簡易 = 月家賃合計 ÷ 月返済合計（業界定番。厳密 NOI ではない）。目安
          1.2×以上。
        </p>
        <table style={{ marginTop: 8 }}>
          <tbody>
            <tr>
              <td>レントロール合計</td>
              <td>
                <strong>{fmtYen(portfolioRent)}／月</strong>
              </td>
            </tr>
            <tr>
              <td>物件ローン月返済合計</td>
              <td>
                <strong>{fmtYen(portfolioPay)}／月</strong>
              </td>
            </tr>
            <tr>
              <td>家賃−返済</td>
              <td>
                <strong>
                  {portfolioPay
                    ? `${portfolioRent - portfolioPay >= 0 ? "+" : ""}${fmtYen(portfolioRent - portfolioPay)}`
                    : "—"}
                </strong>
              </td>
            </tr>
            <tr>
              <td>DSCR（簡易）</td>
              <td>
                <strong>{fmtDscr(portfolioDscr)}</strong>
                <span className="meta"> · {dscrLabel(portfolioDscr)}</span>
              </td>
            </tr>
            <tr>
              <td>YTD 19系CF（Zaim投影・{calendarYear}）</td>
              <td>
                <strong>{fmtYen(Math.round(ytdBucket.cf))}</strong>
                <span className="meta">
                  {" "}
                  · 収 {fmtYen(Math.round(ytdBucket.income))} − 支{" "}
                  {fmtYen(Math.round(ytdBucket.expense))}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <header>
          <span className="lvl">RE-1b</span>
          <strong>
            年計画 vs YTD（{calendarYear}・経過 {throughMonth}ヶ月）
          </strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          計画（比例）= 月次計画 × 経過月。実績 = Zaim 投影の 19系 CF（
          {scope === "combined"
            ? "合算"
            : scope === "personal"
              ? "個人"
              : "法人"}
          ）。合算の月次計画は目標 CF 50万。個人／法人は満室想定 CF を計画に使用。
        </p>
        <table style={{ marginTop: 8 }}>
          <tbody>
            <tr>
              <td>月次計画</td>
              <td>
                <strong>{fmtYen(planProg.planMonthYen)}</strong>
                <span className="meta">
                  {scope === "combined" ? " · 目標50万" : " · 満室想定"}
                </span>
              </td>
            </tr>
            <tr>
              <td>計画 YTD（比例）</td>
              <td>
                <strong>{fmtYen(planProg.planYtdYen)}</strong>
              </td>
            </tr>
            <tr>
              <td>実績 YTD</td>
              <td>
                <strong>{fmtYen(planProg.actualYtdYen)}</strong>
              </td>
            </tr>
            <tr>
              <td>差分（実−計）</td>
              <td>
                <strong>{fmtYenSigned(planProg.deltaYen)}</strong>
                <span className="meta">
                  {planProg.pct != null ? ` · 進捗 ${planProg.pct}%` : ""}
                </span>
              </td>
            </tr>
            {scope === "combined" ? (
              <tr>
                <td>参考: 満室想定との進捗</td>
                <td className="meta">
                  計画比例 {fmtYen(assumedProg.planYtdYen)} · 進捗{" "}
                  {assumedProg.pct != null ? `${assumedProg.pct}%` : "—"}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        <div
          style={{
            marginTop: 12,
            height: 10,
            background: "var(--border, #e0e0e0)",
            borderRadius: 5,
            overflow: "hidden",
          }}
          title={planProg.pct != null ? `${planProg.pct}%` : undefined}
        >
          <div
            style={{
              width: `${barPct}%`,
              height: "100%",
              background:
                (planProg.pct ?? 0) >= 100
                  ? "#2e7d32"
                  : (planProg.pct ?? 0) >= 80
                    ? "#f9a825"
                    : "#c62828",
            }}
          />
        </div>
      </div>

      <div className="card notice">
        <header>
          <span className="lvl">③-A</span>
          <strong>
            想定と実のキャッシュフロー（{calendarYear}・{reBoard.throughLabel}）
          </strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          満室想定はレントロール年収−返済。実の定常はローン・管理・毎月経費だけ。
          取得税・固都税・修繕・年払い保険は特別支出に分けます。
          {reBoard.liveTotal > 0
            ? ` 現況 ${reBoard.liveOccupied}/${reBoard.liveTotal}戸。`
            : ""}
        </p>
        <table>
          <tbody>
            <tr>
              <td>想定CF（満室）</td>
              <td>
                <strong>{fmtYen(Math.round(reBoard.assumedCfMonth))}/月</strong>
                <span className="meta">
                  {" "}
                  · 家賃 {fmtYen(Math.round(reBoard.assumedRentMonth))} − 返済{" "}
                  {fmtYen(Math.round(reBoard.assumedPayMonth))}
                </span>
              </td>
            </tr>
            <tr>
              <td>実CF（定常）</td>
              <td>
                <strong>
                  {reBoard.steadyCfMonth != null
                    ? `${fmtYen(Math.round(reBoard.steadyCfMonth))}/月`
                    : "—"}
                </strong>
                <span className="meta">
                  {reBoard.actualRentMonth != null
                    ? ` · 実家賃 ${fmtYen(Math.round(reBoard.actualRentMonth))} − 返済 ${fmtYen(Math.round(reBoard.actualLoanMonth ?? 0))} − 経費 ${fmtYen(Math.round(reBoard.actualOpexMonth ?? 0))}`
                    : ""}
                </span>
              </td>
            </tr>
            <tr>
              <td>家賃の差（空室・未入金・NET）</td>
              <td>
                {reBoard.rentGapMonth != null
                  ? fmtYenSigned(Math.round(reBoard.rentGapMonth))
                  : "—"}
                <span className="meta">
                  {reBoard.liveOccupied === reBoard.liveTotal &&
                  reBoard.liveTotal > 0
                    ? " · いま満室。差はキャンペーン賃料・管理会社差引後・入金タイミング"
                    : " · 想定家賃 − 財務の実家賃"}
                </span>
              </td>
            </tr>
            {reBoard.rentByBank.length > 0 ? (
              <tr>
                <td>実家賃の入金口座（19.1）</td>
                <td>
                  {reBoard.rentByBank.map((b) => (
                    <div key={b.id}>
                      {b.label} {fmtYen(Math.round(b.yen))}
                    </div>
                  ))}
                  <div className="meta">
                    Grandole I は PayPay が主。LEAF は京都にも残る（併用）。LUUP・保険金は含めない。
                  </div>
                </td>
              </tr>
            ) : null}
            <tr>
              <td>会計の月次（特別込み）</td>
              <td>
                {reBoard.accountingCfMonth != null
                  ? fmtYen(Math.round(reBoard.accountingCfMonth))
                  : "—"}
                <span className="meta">
                  {" "}
                  · ここがマイナスでも、一時費用の割り戻しであることが多い
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <p className="meta" style={{ marginTop: 10 }}>
          ローン正本の月返済合計（loan-tracker 投影）:{" "}
          {loanTrackerPayMonth > 0 ? fmtYen(Math.round(loanTrackerPayMonth)) : "—"}
          ／月（想定返済 {fmtYen(Math.round(reBoard.assumedPayMonth))} と比較用）
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">特別支出のカバー</span>
          <strong>
            {reBoard.coverShortfall == null
              ? "—"
              : reBoard.coverShortfall <= 0
                ? "年換算定常CFで賄える"
                : `不足 ${fmtYen(Math.round(reBoard.coverShortfall))}`}
          </strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          定常月次 × 12 ={" "}
          {reBoard.annualSteady != null
            ? fmtYen(Math.round(reBoard.annualSteady))
            : "—"}
          。{reBoard.throughLabel}の特別支出合計{" "}
          {fmtYen(Math.round(reBoard.specialYtd))}
          {reBoard.coverRatio != null
            ? ` · カバー率 ${Math.round(reBoard.coverRatio * 100)}%`
            : ""}
          。
        </p>
        {reBoard.specials.length > 0 ? (
          <table>
            <tbody>
              {reBoard.specials.map((s) => (
                <tr key={s.kind}>
                  <td>{SPECIAL_LABEL[s.kind]}</td>
                  <td className="num">{fmtYen(Math.round(s.yen))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="meta">特別支出はまだ集計されていません。</p>
        )}
      </div>

      <div className="card" style={{ borderColor: "var(--accent, #c45c26)" }}>
        <header>
          <span className="lvl">目標</span>
          <strong>CF 月50万円</strong>
        </header>
        <table>
          <tbody>
            <tr>
              <td>想定（満室）とのギャップ</td>
              <td>
                <strong>{fmtYen(Math.round(assumedGap))}</strong>
              </td>
            </tr>
            <tr>
              <td>定常とのギャップ</td>
              <td>
                {reBoard.steadyCfMonth != null
                  ? fmtYen(Math.round(CF_GOAL_MONTH - reBoard.steadyCfMonth))
                  : "—"}
              </td>
            </tr>
            <tr>
              <td>LP前年（参考）</td>
              <td>{cfAnnual != null ? fmtYen(cfAnnual) : "—"}</td>
            </tr>
            <tr>
              <td>買い進め Excel</td>
              <td>
                {buyPlan
                  ? `${buyPlan.label || buyPlan.version_key}（${buyPlan.as_of}）`
                  : "未取込"}
              </td>
            </tr>
          </tbody>
        </table>
        <p className="meta" style={{ marginTop: 8 }}>
          詳細: <code>docs/KURASHIFT_CF正規化メモ.md</code>
          {" · "}
          <a href="/roi">物件ごとの満室CF →</a>
          {" · "}
          <a href="/realestate/deals">千三つファネル →</a>
        </p>
      </div>

      <div className="card notice">
        <header>
          <span className="lvl">Lanes</span>
          <strong>4レーン（分離）</strong>
        </header>
        <ul className="meta" style={{ paddingLeft: 18, marginTop: 8 }}>
          <li>
            <a href="/realestate">A 運用</a> — 今のCF・DSCR・ギャップ（この画面）
          </li>
          <li>
            <a href="/realestate/buy-plan">B 買い進めプラン</a> — 長期年表・今狙う条件
            {buyPlan
              ? ` · ${buyPlan.label || buyPlan.version_key}`
              : " · 未取込"}
          </li>
          <li>
            <a href="/realestate/deals">B 千三つ</a> — 情報→内見→買付→融資→購入
          </li>
          <li>
            <a href="/realestate/properties">C 保有</a> — レントロール vs 月返済
          </li>
          <li>
            <a href="/realestate/finance-pack">D 融資パック</a> — 提出書類
          </li>
        </ul>
      </div>

      <div className="card">
        <header>
          <span className="lvl">B-RATE-4</span>
          <strong>正味の利率（表面利回り − ローン金利）</strong>
        </header>
        <p className="meta">
          満室年収÷本体価格の表面利回りからローン金利を引いた参考％。利子が高い負債から返す判断に使う。
          保険の契約者貸付利率は <a href="/portfolio">資産</a> を参照。
        </p>
        <p className="meta" style={{ marginTop: 8 }}>
          {liabilityRates.realEstateNote}
          {" · "}
          <a href="/realestate/properties">物件マスタ（ローン投影）→</a>
          {" · "}
          <a
            href="https://loan-tracker-plum.vercel.app/"
            target="_blank"
            rel="noreferrer"
          >
            loan-tracker
          </a>
        </p>
        <p className="meta" style={{ marginTop: 8 }}>
          合算金利 = Σ(残高×金利) ÷ Σ残高（物件紐づけローン）。正味 =
          表面利回り − 合算金利。計算式:{" "}
          <code>docs/KURASHIFT_loan_tracker_Discover.md</code> §B-RATE-4
        </p>
        {bRate4.length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            保有物件がありません。
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>物件</th>
                <th>名義</th>
                <th className="num">レントロール</th>
                <th className="num">月返済</th>
                <th className="num">家賃−返済</th>
                <th className="num">DSCR</th>
                <th className="num">表面利回り</th>
                <th className="num">合算金利</th>
                <th className="num">正味</th>
                <th className="num">残高合計</th>
              </tr>
            </thead>
            <tbody>
              {bRate4.map((r) => {
                const rent = rentByProp.get(r.propertyId) ?? null;
                const pay = r.monthlyPaymentJpy;
                const gap =
                  rent != null && pay != null ? rent - pay : null;
                const dscr = simpleDscr(rent, pay);
                return (
                  <tr key={r.propertyId}>
                    <td>{r.name}</td>
                    <td className="meta">{r.owner}</td>
                    <td className="num">
                      {rent != null ? (
                        <strong>{fmtYen(rent)}／月</strong>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="num meta">
                      {pay != null ? `${fmtYen(pay)}／月` : "—"}
                    </td>
                    <td className="num">
                      {gap == null ? (
                        "—"
                      ) : (
                        <strong>
                          {gap >= 0 ? "+" : ""}
                          {fmtYen(gap)}
                        </strong>
                      )}
                    </td>
                    <td className="num">
                      <strong>{fmtDscr(dscr)}</strong>
                      <div className="meta">{dscrLabel(dscr)}</div>
                    </td>
                    <td className="num meta">{fmtPct(r.surfaceYieldPct)}</td>
                    <td className="num meta">{fmtPct(r.loanRatePct)}</td>
                    <td className="num">
                      <strong>{fmtPct(r.netSpreadPct)}</strong>
                    </td>
                    <td className="num meta">
                      {r.balanceJpy != null ? fmtYen(r.balanceJpy) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="card-grid">
        <div className="card">
          <header>
            <span className="lvl">③-A</span>
            <strong>運用・計画進捗</strong>
          </header>
          <p>
            <strong>今持っている資産</strong>が、年間計画に対して現在どうか（YTD・差分・補正）。
          </p>
          <ul className="meta">
            <li>個人／法人／合算切替</li>
            <li>実績 → 計画 → 進捗 → ギャップ → 補正</li>
            <li>入口: このページ（将来の既定タブ）</li>
          </ul>
        </div>

        <div className="card">
          <header>
            <span className="lvl">③-B</span>
            <strong>新規購入検討</strong>
          </header>
          <p>
            <strong>これから買う物件</strong>の検討を案件としてまとめる（千三つファネル）。
          </p>
          <ul className="meta">
            <li>
              情報 {funnelCounts.info} · 内見 {funnelCounts.viewing} · 買付{" "}
              {funnelCounts.offer} · 融資 {funnelCounts.loan} · 購入{" "}
              {funnelCounts.purchased} · 見送り {funnelCounts.passed}
            </li>
            <li>取得後 → ③-A の計画へ／LP 物件購入モード</li>
            <li>
              入口: <a href="/realestate/deals">/realestate/deals</a>
            </li>
          </ul>
        </div>
      </div>

      <div className="card-grid">
        <div className="card">
          <header>
            <span className="lvl">③-C</span>
            <strong>保有物件マスタ</strong>
          </header>
          <p>
            <strong>今所有している物件</strong>の基本情報。ローンは
            <a
              href="https://loan-tracker-plum.vercel.app/"
              target="_blank"
              rel="noreferrer"
            >
              借入残高トラッカー
            </a>
            を正本として連携（二重入力しない）。
          </p>
          <ul className="meta">
            <li>法人／個人の物件一覧</li>
            <li>既存: property_units・property_info.yaml</li>
            <li>
              入口: <a href="/realestate/properties">/realestate/properties</a>
            </li>
          </ul>
        </div>

        <div className="card">
          <header>
            <span className="lvl">③-D</span>
            <strong>融資提出パック</strong>
          </header>
          <p>
            融資時の<strong>提出書類一覧</strong>。必要事項を入力し、
            <strong>銀行向けに出力</strong>。
          </p>
          <ul className="meta">
            <li>書類 × 状態 × 入力フィールドの表</li>
            <li>③-C・240_融資・法人情報を参照</li>
            <li>
              入口:{" "}
              <a href="/realestate/finance-pack">/realestate/finance-pack</a>
              （チェックリスト骨格）
            </li>
          </ul>
        </div>
      </div>

      <div className="card-grid">
        <div className="card">
          <header>
            <span className="lvl">Theme</span>
            <strong>大きな判断</strong>
          </header>
          <p>
            修繕・借換え・売却（③-A）／新規取得（③-B）は Theme 承認フロー（レーン{" "}
            <code>realestate</code>）。
          </p>
          <a className="btn secondary" href="/themes">
            テーマ一覧へ
          </a>
        </div>
      </div>

      <div className="card">
        <header>
          <span className="lvl">Bridge</span>
          <strong>いま見えるデータ（個人・LP スナップ）</strong>
        </header>
        {latestSnap && re19 ? (
          <table>
            <tbody>
              <tr>
                <td>スナップ</td>
                <td>
                  {latestSnap.label}（{latestSnap.snapshot_at}）
                </td>
              </tr>
              <tr>
                <td>19不動産 収入</td>
                <td>{fmtYen(re19.income_jpy ?? 0)}</td>
              </tr>
              <tr>
                <td>19不動産 支出</td>
                <td>{fmtYen(re19.expense_jpy ?? 0)}</td>
              </tr>
              <tr>
                <td>CF（収入−支出）</td>
                <td>
                  <strong>{fmtYen(re19.cf_jpy ?? 0)}</strong>
                </td>
              </tr>
              <tr>
                <td>登録号室（稼働参考）</td>
                <td>{unitCount ?? 0} 件</td>
              </tr>
            </tbody>
          </table>
        ) : (
          <p className="meta">
            {actualsYear}{" "}
            年度（実績年）の LP スナップがありません。{" "}
            <a href="/lifeplan?mode=annual">ライフプラン</a>
            で Step1「年度実績を取り込む」を実行すると 19不動産の橋渡し表示が出ます。
          </p>
        )}
        <p className="meta" style={{ marginTop: "0.75rem" }}>
          関連: <a href="/lifeplan?mode=re_purchase">物件購入モード</a>
          {" · "}
          <a href="/roi">ROI（物件ごと）</a>
        </p>
      </div>
    </Shell>
  );
}

