import {
  fmtYen,
  parseOccupancySummary,
  previousYmJst,
  summarizeUnits,
  type PropertyUnit,
} from "@/lib/occupancy";
import { buildCashflowInsight } from "@/lib/cashflowInsight";
import { createClient } from "@/lib/supabase/server";
import { fmtYenSigned } from "./homeHelpers";

export default async function HomeMetricsBand() {
  const supabase = await createClient();
  const { data: meta } = await supabase.from("sync_meta").select("key,value");
  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));

  const targetYm = previousYmJst();
  const { data: metricRows } = await supabase
    .from("metrics")
    .select("metric,entity,value,recorded_at")
    .in("metric", [
      "cashflow",
      "rent_income",
      "rental_expense",
      "expense_total",
      "income_total",
      "other_expense",
      "other_income",
      "salary",
      "repair_expense",
    ])
    .order("recorded_at", { ascending: false })
    .limit(400);

  const metricLatest = new Map<string, number>();
  const metricMonths = new Set<string>();
  for (const r of metricRows || []) {
    const ym = String(r.recorded_at).slice(0, 7);
    metricMonths.add(ym);
    const key = `${ym}|${r.entity}|${r.metric}`;
    if (!metricLatest.has(key)) metricLatest.set(key, Number(r.value));
  }
  const financeYm = metricMonths.has(targetYm)
    ? targetYm
    : [...metricMonths].sort().reverse().find(
        (ym) =>
          metricLatest.has(`${ym}|corporate|cashflow`) ||
          metricLatest.has(`${ym}|personal|cashflow`),
      ) || targetYm;
  const pickMetric = (ent: string, metric: string, ym = financeYm) =>
    metricLatest.get(`${ym}|${ent}|${metric}`);

  const prevYmForFinance = (() => {
    const [y, m] = financeYm.split("-").map(Number);
    if (!y || !m) return null;
    if (m === 1) return `${y - 1}-12`;
    return `${y}-${String(m - 1).padStart(2, "0")}`;
  })();

  const sliceFor = (ent: "corporate" | "personal", ym: string) => ({
    cashflow: pickMetric(ent, "cashflow", ym),
    rent_income: pickMetric(ent, "rent_income", ym),
    rental_expense: pickMetric(ent, "rental_expense", ym),
    expense_total: pickMetric(ent, "expense_total", ym),
    income_total: pickMetric(ent, "income_total", ym),
    other_expense: pickMetric(ent, "other_expense", ym),
    other_income: pickMetric(ent, "other_income", ym),
    salary: pickMetric(ent, "salary", ym),
    repair_expense: pickMetric(ent, "repair_expense", ym),
  });

  const corpCur = sliceFor("corporate", financeYm);
  const persCur = sliceFor("personal", financeYm);
  const corpPrev = prevYmForFinance ? sliceFor("corporate", prevYmForFinance) : null;
  const persPrev = prevYmForFinance ? sliceFor("personal", prevYmForFinance) : null;
  const corpInsight = buildCashflowInsight("corporate", corpCur, corpPrev);
  const persInsight = buildCashflowInsight("personal", persCur, persPrev);

  const { data: unitRows } = await supabase
    .from("property_units")
    .select(
      "id,property_id,property_name,room,status,rent,note,source,payload,updated_at",
    )
    .order("property_id")
    .order("room");
  const units = (unitRows || []) as PropertyUnit[];
  const fromUnits = summarizeUnits(units);
  const occupancy =
    fromUnits.total > 0
      ? fromUnits
      : parseOccupancySummary(metaMap.occupancy_summary) || fromUnits;

  return (
    <div className="home-band home-band-metrics">
      <div className="home-band-head">
        <h2 className="home-band-title">モチベーション数値</h2>
        <p className="home-band-sub">
          いちばん上は入居率。減っていたら埋めていく。
          {" · 表示月 "}
          {financeYm}
          {financeYm !== targetYm ? `（先月 ${targetYm} は未取込）` : ""}
          {" · 手残り＝収入合計−支出合計（振替除く）"}
        </p>
      </div>

      <div
        className={
          occupancy.total && occupancy.rate_pct >= 100
            ? "home-occupancy-hero is-full"
            : occupancy.total
              ? "home-occupancy-hero is-gap"
              : "home-occupancy-hero"
        }
        aria-label="入居率"
      >
        <div className="home-occupancy-hero-main">
          <span className="home-occupancy-hero-label">入居率</span>
          <strong className="home-occupancy-hero-value">
            {occupancy.total ? `${occupancy.rate_pct}%` : "—"}
          </strong>
        </div>
        <div className="home-occupancy-hero-side">
          {occupancy.total ? (
            <>
              <p className="home-occupancy-hero-count">
                {occupancy.occupied}/{occupancy.total}戸
                {occupancy.vacant > 0
                  ? ` · 空室 ${occupancy.vacant}戸`
                  : " · 満室"}
              </p>
              {occupancy.rate_pct >= 100 ? (
                <p className="home-occupancy-hero-msg">
                  100%。この状態を守る。
                </p>
              ) : (
                <p className="home-occupancy-hero-msg">
                  100%まで埋めていく。
                  {occupancy.vacant_labels?.length
                    ? ` 空室: ${occupancy.vacant_labels.join("、")}`
                    : ""}
                </p>
              )}
            </>
          ) : (
            <p className="home-occupancy-hero-msg">号室データ未取込</p>
          )}
          <a href="/properties" className="home-more">
            所有物件へ →
          </a>
        </div>
      </div>

      <div className="cf-panels">
        {(
          [
            {
              key: "corporate",
              title: "法人",
              cur: corpCur,
              insight: corpInsight,
              showSalary: false,
            },
            {
              key: "personal",
              title: "個人",
              cur: persCur,
              insight: persInsight,
              showSalary: true,
            },
          ] as const
        ).map((panel) => {
          const cf = panel.cur.cashflow;
          const cfClass =
            cf == null ? "" : cf >= 0 ? "is-plus" : "is-minus";
          return (
            <article key={panel.key} className={`cf-panel ${cfClass}`}>
              <header className="cf-panel-head">
                <h3>{panel.title}</h3>
              </header>

              <div className="cf-hero">
                <span className="cf-hero-label">手残り</span>
                <strong className="cf-hero-value">{fmtYen(cf)}</strong>
              </div>

              <div className="cf-stack" aria-label="家賃と支出の関係">
                <div className="cf-row is-in">
                  <span>家賃</span>
                  <strong>{fmtYen(panel.cur.rent_income)}</strong>
                </div>
                {panel.showSalary ? (
                  <div className="cf-row is-in">
                    <span>給与・賞与</span>
                    <strong>{fmtYen(panel.cur.salary)}</strong>
                  </div>
                ) : null}
                {(panel.cur.other_income ?? 0) > 0 ? (
                  <div className="cf-row is-in">
                    <span>その他収入</span>
                    <strong>{fmtYen(panel.cur.other_income)}</strong>
                  </div>
                ) : null}
                <div className="cf-row is-out">
                  <span>賃貸支出（ローン・管理など）</span>
                  <strong>
                    {fmtYenSigned(panel.cur.rental_expense, "-")}
                  </strong>
                </div>
                {(panel.cur.repair_expense ?? 0) > 0 ? (
                  <div className="cf-row is-out">
                    <span>修繕</span>
                    <strong>
                      {fmtYenSigned(panel.cur.repair_expense, "-")}
                    </strong>
                  </div>
                ) : null}
                <div className="cf-row is-out">
                  <span>その他支出（固定費など）</span>
                  <strong>
                    {fmtYenSigned(panel.cur.other_expense, "-")}
                  </strong>
                </div>
                <div className="cf-row is-result">
                  <span>→ 手残り</span>
                  <strong>{fmtYen(cf)}</strong>
                </div>
              </div>

              <div className={`cf-insight tone-${panel.insight.tone}`}>
                <p className="cf-insight-head">{panel.insight.headline}</p>
                <p className="cf-insight-body">{panel.insight.body}</p>
                <p className="cf-insight-path">{panel.insight.path}</p>
              </div>
            </article>
          );
        })}
      </div>

      <p className="home-metrics-more">
        <a href="/metrics" className="home-more">
          収支・数値の詳細 →
        </a>
      </p>
    </div>
  );
}
