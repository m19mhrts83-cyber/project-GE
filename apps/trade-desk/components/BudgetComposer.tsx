"use client";

import { fmtYen } from "@/lib/format";
import type { BudgetLine } from "@/lib/budgetCompose";

const MONTHS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"];

function BarChart({
  rows,
}: {
  rows: { year: number; plan: number; actual: number | null }[];
}) {
  const max = Math.max(
    1,
    ...rows.flatMap((r) => [r.plan, r.actual ?? 0])
  );
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
      </div>
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
  return (
    <>
      <article className="card" style={{ marginBottom: 16 }}>
        <header>
          <span className="lvl">推移</span>
          <strong>過去{lookbackYears.length}年の計画と実績</strong>
        </header>
        <BarChart rows={totals} />
      </article>

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
              return (
                <tr key={line.category}>
                  <td className="sticky-col">{line.category}</td>
                  {lookbackYears.map((y) => (
                    <td key={`a${y}`} className="num">
                      {line.actualAnnual[y] != null
                        ? fmtYen(line.actualAnnual[y])
                        : "—"}
                    </td>
                  ))}
                  {lookbackYears.map((y) => (
                    <td key={`p${y}`} className="num">
                      {line.planAnnual[y] != null ? fmtYen(line.planAnnual[y]) : "—"}
                    </td>
                  ))}
                  {line.months.map((amt, i) => (
                    <td key={i} className="num">
                      {amt ? fmtYen(amt) : "—"}
                    </td>
                  ))}
                  <td className="num">
                    <strong>{fmtYen(annual)}</strong>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="meta" style={{ marginTop: 10 }}>
        月別の数字は Numbers「表1.月別予算設定」の最新版です。セルの直接編集は次のフェーズで、今は年次更新のステップから Jarvis 経由で直します。
      </p>
    </>
  );
}
