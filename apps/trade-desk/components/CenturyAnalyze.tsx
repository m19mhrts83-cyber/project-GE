"use client";

import { useMemo, useState } from "react";
import { fmtManUnit } from "@/lib/format";
import {
  centuryMilestones,
  evalTotalPlan,
  shinjiAgeInYear,
  yearsWithActuals,
  type CenturyModel,
  type LifeEventModel,
} from "@/lib/centuryPlan";

type Overlay = { key: string; label: string; values: (number | null)[] };

function OverlayChart({
  years,
  series,
  markers,
}: {
  years: number[];
  series: Overlay[];
  markers: { year: number; label: string }[];
}) {
  const pts = series.flatMap((s) =>
    years.map((y, i) => ({ y, v: s.values[i] })).filter((p): p is { y: number; v: number } => p.v != null)
  );
  if (pts.length < 2) return <p className="meta">重ねる計画値が足りません。</p>;
  const w = 760;
  const h = 220;
  const pad = 22;
  const vs = pts.map((p) => p.v);
  const min = Math.min(0, ...vs);
  const max = Math.max(0, ...vs);
  const span = max - min || 1;
  const x0 = years[0];
  const x1 = years[years.length - 1];
  const xspan = x1 - x0 || 1;
  const xy = (year: number, v: number) => {
    const x = pad + ((year - x0) / xspan) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return { x, y };
  };
  const colors = ["var(--ink-blue)", "#6b8cae", "#9aa8b5", "#c4a574"];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="lp-spark lp-analyze-spark" role="img" aria-label="計画版の重ね合わせ">
      <line x1={pad} x2={w - pad} y1={xy(x0, 0).y} y2={xy(x0, 0).y} className="lp-spark-zero" />
      {markers.map((m) => {
        const x = xy(m.year, 0).x;
        return (
          <g key={m.label}>
            <line x1={x} x2={x} y1={pad} y2={h - pad} className="lp-spark-now" />
            <text x={x + 3} y={pad + 10} className="lp-analyze-lab">
              {m.label}
            </text>
          </g>
        );
      })}
      {series.map((s, i) => {
        const list = years
          .map((y, idx) => ({ y, v: s.values[idx] }))
          .filter((p): p is { y: number; v: number } => p.v != null);
        if (list.length < 2) return null;
        const points = list.map((p) => {
          const { x, y } = xy(p.y, p.v);
          return `${x},${y}`;
        }).join(" ");
        return (
          <polyline
            key={s.key}
            fill="none"
            points={points}
            stroke={colors[i % colors.length]}
            strokeWidth={i === 0 ? 2.6 : 1.6}
            opacity={i === 0 ? 1 : 0.75}
          />
        );
      })}
    </svg>
  );
}

function YearBars({
  rows,
}: {
  rows: { year: number; plan: number | null; actual: number | null }[];
}) {
  if (!rows.length) return <p className="meta">実績のある年がまだありません。</p>;
  const max = Math.max(
    1,
    ...rows.flatMap((r) => [r.plan ?? 0, r.actual ?? 0]).map((v) => Math.abs(v))
  );
  return (
    <div className="lp-year-bars">
      {rows.map((r) => {
        const planH = r.plan == null ? 0 : (Math.abs(r.plan) / max) * 100;
        const actH = r.actual == null ? 0 : (Math.abs(r.actual) / max) * 100;
        return (
          <div key={r.year} className="lp-yb">
            <div className="lp-yb-cols">
              <div
                className={`lp-yb-bar plan${(r.plan ?? 0) < 0 ? " neg" : ""}`}
                style={{ height: `${planH}%` }}
                title={`計画 ${fmtManUnit(r.plan)}`}
              />
              <div
                className={`lp-yb-bar actual${(r.actual ?? 0) < 0 ? " neg" : ""}`}
                style={{ height: `${actH}%` }}
                title={`実績 ${fmtManUnit(r.actual)}`}
              />
            </div>
            <div className="lp-yb-y">{r.year}</div>
          </div>
        );
      })}
    </div>
  );
}

export default function CenturyAnalyze({
  models,
  events,
}: {
  models: CenturyModel[];
  events: LifeEventModel | null;
}) {
  const current = models[0];
  const [focusYear, setFocusYear] = useState<number | null>(null);
  const years = current?.years ?? [];
  const actualYears = current ? yearsWithActuals(current) : [];
  const yearForMix =
    focusYear ?? actualYears[actualYears.length - 1] ?? new Date().getFullYear();
  const expenseMix = useMemo(() => {
    if (!current) return [];
    return current.lines
      .filter((l) => l.section === "expense" && l.series === "plan" && !l.isTotal)
      .map((l) => ({
        group: l.group,
        label: l.label,
        v: l.values[yearForMix] ?? null,
      }))
      .filter((r) => r.v != null && Math.abs(r.v) >= 1)
      .sort((a, b) => Math.abs(b.v!) - Math.abs(a.v!));
  }, [current, yearForMix]);

  if (!current) {
    return <p className="meta">分析できる計画データがありません。</p>;
  }
  const overlays: Overlay[] = models.map((m, i) => {
    const line = evalTotalPlan(m);
    return {
      key: m.versionKey,
      label: i === 0 ? `最新 ${m.versionKey}` : m.versionKey,
      values: years.map((y) => line?.values[y] ?? null),
    };
  });
  const markers = centuryMilestones(current, events).map((m) => ({
    year: m.year,
    label: `${m.year} ${m.title}`,
  }));
  const evalPlan = evalTotalPlan(current);
  const evalActual = current.lines.find(
    (l) => l.section === "eval" && l.series === "actual" && l.label.includes("合計")
  );
  const barRows = (actualYears.length ? actualYears : years.filter((y) => y <= new Date().getFullYear()))
    .filter((y) => years.includes(y))
    .map((year) => ({
      year,
      plan: evalPlan?.values[year] ?? null,
      actual: evalActual?.values[year] ?? null,
    }));

  const tableYears = years.filter((y) => y >= (actualYears[0] ?? years[0]) && y <= new Date().getFullYear() + 5);

  return (
    <>
      <div className="grid" style={{ marginBottom: 16 }}>
        <article className="card">
          <header>
            <span className="lvl">版を重ねる</span>
            <strong>貯蓄可能額・計画の推移</strong>
          </header>
          <p className="meta" style={{ margin: "0 0 8px" }}>
            太い線が最新版。細い線は過去の計画版です。
          </p>
          <OverlayChart years={years} series={overlays} markers={markers} />
          <div className="lp-bar-legend meta" style={{ marginTop: 8 }}>
            {overlays.map((s, i) => (
              <span key={s.key} style={{ marginRight: 10 }}>
                {i === 0 ? "●" : "○"} {s.label}
              </span>
            ))}
          </div>
        </article>
        <article className="card">
          <header>
            <span className="lvl">実績を重ねる</span>
            <strong>計画 vs 実績（実績のある年）</strong>
          </header>
          <YearBars rows={barRows} />
          <div className="lp-bar-legend meta" style={{ marginTop: 8 }}>
            <span className="swatch plan" /> 計画
            <span className="swatch actual" /> 実績
          </div>
        </article>
      </div>

      <article className="card" style={{ marginBottom: 16 }}>
        <header>
          <span className="lvl">{yearForMix}年</span>
          <strong>支出の内訳（計画）</strong>
        </header>
        <div className="lp-chips" style={{ margin: "8px 0" }}>
          {barRows.map((r) => (
            <button
              key={r.year}
              type="button"
              className={`lp-chip${yearForMix === r.year ? " active" : ""}`}
              onClick={() => setFocusYear(r.year)}
            >
              {r.year}
            </button>
          ))}
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>分類</th>
                <th>項目</th>
                <th className="num">計画</th>
              </tr>
            </thead>
            <tbody>
              {expenseMix.slice(0, 16).map((r) => (
                <tr key={`${r.group}-${r.label}`}>
                  <td>{r.group}</td>
                  <td>{r.label}</td>
                  <td className="num">{fmtManUnit(r.v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>

      <article className="card">
        <header>
          <span className="lvl">年次</span>
          <strong>計画・実績・年齢</strong>
        </header>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>西暦</th>
                <th>真治</th>
                <th className="num">計画</th>
                <th className="num">実績</th>
                <th className="num">差（実績−計画）</th>
              </tr>
            </thead>
            <tbody>
              {tableYears.map((y) => {
                const plan = evalPlan?.values[y] ?? null;
                const actual = evalActual?.values[y] ?? null;
                const gap = plan != null && actual != null ? actual - plan : null;
                const age = shinjiAgeInYear(events, y);
                return (
                  <tr key={y}>
                    <td>{y}</td>
                    <td>{age != null ? `${age}歳` : "—"}</td>
                    <td className="num">{fmtManUnit(plan)}</td>
                    <td className="num">{fmtManUnit(actual)}</td>
                    <td className="num">{gap == null ? "—" : fmtManUnit(gap)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </article>
    </>
  );
}
