"use client";

import { fmtYen } from "@/lib/format";
import {
  groupBySection,
  type BudgetLine,
  type BudgetSection,
} from "@/lib/budgetCompose";

const MONTHS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"];

function BarChart({
  rows,
}: {
  rows: { year: number; plan: number; actual: number | null }[];
}) {
  const max = Math.max(1, ...rows.flatMap((r) => [r.plan, r.actual ?? 0]));
  return (
    <div className="lp-bars" role="img" aria-label="年次の計画と実績">
      {rows.map((r) => (
        <div key={r.year} className="lp-bar-col">
          <div className="lp-bar-pair">
            <div
              className="lp-bar plan"
              style={{ height: `${Math.round((r.plan / max) * 120)}px` }}
              title={`計画 ${fmtYen(r.plan)}`}
            />
            <div
              className="lp-bar actual"
              style={{
                height: `${r.actual != null ? Math.round((r.actual / max) * 120) : 0}px`,
                opacity: r.actual != null ? 1 : 0.25,
              }}
              title={r.actual != null ? `実績 ${fmtYen(r.actual)}` : "実績なし"}
            />
          </div>
          <div className="meta">{r.year}</div>
        </div>
      ))}
      <div className="lp-bar-legend meta">
        <span className="swatch plan" /> 計画
        <span className="swatch actual" /> 実績
        <span className="meta">（家計＋教育。不動産・収入は下表）</span>
      </div>
    </div>
  );
}

function SectionHint({ section }: { section: BudgetSection }) {
  if (section === "education") {
    return (
      <p className="meta" style={{ margin: "0 0 8px" }}>
        こども教育・学費・学資・雑費。過去実績を見ながら 2026 の月別を確認します。
      </p>
    );
  }
  if (section === "realestate") {
    return (
      <p className="meta" style={{ margin: "0 0 8px" }}>
        家賃収入と賃貸経費（19系）。家計予算表には無いので、ここで内訳を見ます。
        収入行は実績の収入額、支出行は経費額です。
      </p>
    );
  }
  if (section === "income") {
    return (
      <p className="meta" style={{ margin: "0 0 8px" }}>
        給与・賞与など（参考）。予算月別の対象外です。
      </p>
    );
  }
  return (
    <p className="meta" style={{ margin: "0 0 8px" }}>
      住まい・食費・交際・保険・クルマ・投資など。
    </p>
  );
}

function LinesTable({
  planYear,
  lookbackYears,
  lines,
}: {
  planYear: number;
  lookbackYears: number[];
  lines: BudgetLine[];
}) {
  return (
    <div className="table-scroll">
      <table className="century-table">
        <thead>
          <tr>
            <th className="sticky-col">費目</th>
            {lookbackYears.map((y) => (
              <th key={`a${y}`} className="num">
                {y}実績
              </th>
            ))}
            {lookbackYears.map((y) => (
              <th key={`p${y}`} className="num">
                {y}計画
              </th>
            ))}
            {MONTHS.map((m) => (
              <th key={m} className="num">
                {planYear}/{m}
              </th>
            ))}
            <th className="num">{planYear}計</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => {
            const annual = line.months.reduce((s, n) => s + n, 0);
            const showMonths = line.fromPlan || annual > 0;
            return (
              <tr key={`${line.section}-${line.categoryKey || line.category}`}>
                <td className="sticky-col">
                  {line.category}
                  {!line.fromPlan ? (
                    <div className="meta">実績のみ（計画表に無し）</div>
                  ) : null}
                </td>
                {lookbackYears.map((y) => (
                  <td key={`a${y}`} className="num">
                    {line.actualAnnual[y] != null
                      ? fmtYen(line.actualAnnual[y])
                      : "—"}
                  </td>
                ))}
                {lookbackYears.map((y) => (
                  <td key={`p${y}`} className="num">
                    {line.planAnnual[y] != null
                      ? fmtYen(line.planAnnual[y])
                      : "—"}
                  </td>
                ))}
                {line.months.map((amt, i) => (
                  <td key={i} className="num">
                    {showMonths && amt ? fmtYen(amt) : "—"}
                  </td>
                ))}
                <td className="num">
                  <strong>{showMonths && annual ? fmtYen(annual) : "—"}</strong>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function BudgetComposer({
  planYear,
  lookbackYears,
  lines,
  totals,
}: {
  planYear: number;
  lookbackYears: number[];
  lines: BudgetLine[];
  totals: { year: number; plan: number; actual: number | null }[];
}) {
  const groups = groupBySection(lines);

  return (
    <>
      <article className="card" style={{ marginBottom: 16 }}>
        <header>
          <span className="lvl">推移</span>
          <strong>
            {lookbackYears[0]}–{lookbackYears[lookbackYears.length - 1]}{" "}
            の計画と実績（家計＋教育）
          </strong>
        </header>
        <BarChart rows={totals.filter((t) => lookbackYears.includes(t.year))} />
      </article>

      <p className="meta" style={{ marginBottom: 12 }}>
        {planYear}
        年の月別予算を、過去実績（とくに2022・2023）と教育・不動産の内訳を横に置いて確認する表です。セル編集と年次更新の実行はまだ使いません。
      </p>

      {groups.map((g) => (
        <article className="card" key={g.section} style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">
              {g.section === "education"
                ? "教育"
                : g.section === "realestate"
                  ? "不動産"
                  : g.section === "income"
                    ? "収入"
                    : "家計"}
            </span>
            <strong>{g.label}</strong>
          </header>
          <SectionHint section={g.section} />
          <LinesTable
            planYear={planYear}
            lookbackYears={lookbackYears}
            lines={g.lines}
          />
        </article>
      ))}

      <p className="meta" style={{ marginTop: 4 }}>
        月別の数字は Numbers「表1.月別予算設定」の最新版です。実績は Zaim
        財務（サマリーまたは取引ロールアップ）です。
      </p>
    </>
  );
}
