"use client";

import { useMemo, useState } from "react";
import { fmtManUnit } from "@/lib/format";
import {
  decadesFromYears,
  defaultYearWindow,
  significantDiffs,
  type CenturyDiff,
  type CenturyLine,
  type CenturyModel,
  type SeriesKind,
} from "@/lib/centuryPlan";

type CompareMode = "latest" | "stack" | "toggle";
type SeriesFilter = "both" | "plan" | "actual";

function Sparkline({
  years,
  values,
}: {
  years: number[];
  values: (number | null)[];
}) {
  const pts = years
    .map((y, i) => ({ y, v: values[i] }))
    .filter((p): p is { y: number; v: number } => p.v != null);
  if (pts.length < 2) return <p className="meta">グラフ用の計画値が足りません。</p>;
  const w = 640;
  const h = 140;
  const pad = 12;
  const vs = pts.map((p) => p.v);
  const min = Math.min(0, ...vs);
  const max = Math.max(0, ...vs);
  const span = max - min || 1;
  const x0 = pts[0].y;
  const x1 = pts[pts.length - 1].y;
  const xspan = x1 - x0 || 1;
  const xy = (year: number, v: number) => {
    const x = pad + ((year - x0) / xspan) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return `${x},${y}`;
  };
  const line = pts.map((p) => xy(p.y, p.v)).join(" ");
  const zeroY = h - pad - ((0 - min) / span) * (h - pad * 2);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="lp-spark" role="img" aria-label="貯蓄可能額の推移">
      <line x1={pad} x2={w - pad} y1={zeroY} y2={zeroY} className="lp-spark-zero" />
      <polyline fill="none" points={line} className="lp-spark-line" />
    </svg>
  );
}

function CenturyTable({
  model,
  years,
  seriesFilter,
  highlight,
  overlay,
}: {
  model: CenturyModel;
  years: number[];
  seriesFilter: SeriesFilter;
  highlight?: CenturyDiff[];
  overlay?: CenturyModel | null;
}) {
  const hiYears = new Set(
    (highlight ?? []).filter((d) => d.label.startsWith("合計")).map((d) => d.year)
  );
  const sections: { key: CenturyLine["section"]; title: string }[] = [
    { key: "eval", title: "収支評価" },
    { key: "income", title: "生活収入" },
    { key: "expense", title: "生活支出" },
  ];
  const show = (s: SeriesKind) =>
    seriesFilter === "both" ||
    (seriesFilter === "plan" && s === "plan") ||
    (seriesFilter === "actual" && s === "actual");

  return (
    <div className="table-scroll century-scroll">
      <table className="century-table">
        <thead>
          <tr>
            <th className="sticky-col">項目</th>
            <th>区分</th>
            {years.map((y) => (
              <th key={y} className={`num${hiYears.has(y) ? " hi-year" : ""}`}>
                {y}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sections.map((sec) => {
            const rows = model.lines.filter((l) => l.section === sec.key && show(l.series));
            if (!rows.length) return null;
            return (
              <FragmentSection
                key={sec.key}
                title={sec.title}
                colSpan={years.length + 2}
                rows={rows}
                years={years}
                overlay={overlay}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FragmentSection({
  title,
  colSpan,
  rows,
  years,
  overlay,
}: {
  title: string;
  colSpan: number;
  rows: CenturyLine[];
  years: number[];
  overlay?: CenturyModel | null;
}) {
  return (
    <>
      <tr className="section-row">
        <td colSpan={colSpan}>{title}</td>
      </tr>
      {rows.map((row) => {
        const ov = overlay?.lines.find(
          (l) =>
            l.section === row.section &&
            l.series === row.series &&
            l.label === row.label
        );
        return (
          <tr key={row.id} className={row.isTotal ? "total-row" : undefined}>
            <td className="sticky-col">{row.label}</td>
            <td>{row.series === "plan" ? "計画" : "実績"}</td>
            {years.map((y) => {
              const cur = row.values[y] ?? null;
              const prev = ov?.values[y] ?? null;
              const changed =
                ov &&
                cur != null &&
                prev != null &&
                Math.abs(cur - prev) >= 1;
              return (
                <td
                  key={y}
                  className={`num${changed ? (cur! > prev! ? " diff-pos" : " diff-neg") : ""}`}
                >
                  {fmtManUnit(cur)}
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}

export default function CenturyExplorer({
  current,
  previous,
  diffs,
}: {
  current: CenturyModel;
  previous: CenturyModel | null;
  diffs: CenturyDiff[];
}) {
  const nowYear = new Date().getFullYear();
  const def = defaultYearWindow(nowYear);
  const decades = decadesFromYears(current.years);
  const [range, setRange] = useState<"near" | number | "all">("near");
  const [seriesFilter, setSeriesFilter] = useState<SeriesFilter>("both");
  const [compare, setCompare] = useState<CompareMode>(previous ? "toggle" : "latest");
  const [showBefore, setShowBefore] = useState(false);

  const years = useMemo(() => {
    if (range === "all") return current.years;
    if (range === "near") {
      return current.years.filter((y) => y >= def.start && y <= def.end);
    }
    return current.years.filter((y) => y >= range && y < range + 10);
  }, [current.years, range, def.start, def.end]);

  const sig = significantDiffs(diffs);
  const evalPlan = current.lines.find(
    (l) => l.section === "eval" && l.series === "plan" && l.label.includes("合計")
  );
  const sparkYears = current.years.filter((y) => y >= nowYear - 3 && y <= nowYear + 25);
  const sparkVals = sparkYears.map((y) => evalPlan?.values[y] ?? null);
  const thisYear = evalPlan?.values[nowYear] ?? null;
  const modelShown =
    compare === "toggle" && showBefore && previous ? previous : current;

  return (
    <>
      <div className="grid" style={{ marginBottom: 16 }}>
        <article className="card">
          <header>
            <span className="lvl">閲覧</span>
            <strong>
              {current.label}（{current.asOf}）
            </strong>
          </header>
          <p className="meta" style={{ margin: "0 0 8px" }}>
            Numbers「キャッシュフロー」の最新結果です。単位は万円。日常は閲覧、年1回の更新は予算編成から。
          </p>
          <p style={{ margin: 0, fontSize: "1.35rem", fontWeight: 800 }}>
            {nowYear}年 貯蓄可能額（計画） {fmtManUnit(thisYear)}
          </p>
        </article>
        <article className="card">
          <header>
            <span className="lvl">推移</span>
            <strong>合計・計画（直近〜25年）</strong>
          </header>
          <Sparkline years={sparkYears} values={sparkVals} />
        </article>
      </div>

      {previous ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">差分</span>
            <strong>
              前回 {previous.versionKey} → 今回 {current.versionKey}
            </strong>
          </header>
          {sig.length ? (
            <ul className="meta" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              {sig.slice(0, 6).map((d) => (
                <li key={`${d.label}-${d.year}`}>
                  {d.year}年 {d.label}：{fmtManUnit(d.before)} → {fmtManUnit(d.after)}（
                  {d.delta != null && d.delta > 0 ? "+" : ""}
                  {fmtManUnit(d.delta)}）
                </li>
              ))}
            </ul>
          ) : (
            <p className="meta" style={{ margin: "8px 0 0" }}>
              合計の計画で、5万以上動いた年はありません。
            </p>
          )}
        </div>
      ) : null}

      <div className="lp-toolbar">
        <div className="lp-chips">
          <button
            type="button"
            className={`lp-chip${range === "near" ? " active" : ""}`}
            onClick={() => setRange("near")}
          >
            直近〜12年
          </button>
          {decades.map((d) => (
            <button
              key={d}
              type="button"
              className={`lp-chip${range === d ? " active" : ""}`}
              onClick={() => setRange(d)}
            >
              {d}年代
            </button>
          ))}
          <button
            type="button"
            className={`lp-chip${range === "all" ? " active" : ""}`}
            onClick={() => setRange("all")}
          >
            全期間
          </button>
        </div>
        <div className="lp-chips">
          {(
            [
              ["both", "計画と実績"],
              ["plan", "計画のみ"],
              ["actual", "実績のみ"],
            ] as const
          ).map(([k, lab]) => (
            <button
              key={k}
              type="button"
              className={`lp-chip${seriesFilter === k ? " active" : ""}`}
              onClick={() => setSeriesFilter(k)}
            >
              {lab}
            </button>
          ))}
        </div>
        {previous ? (
          <div className="lp-chips">
            {(
              [
                ["latest", "最新のみ"],
                ["stack", "上下に並べる"],
                ["toggle", "表内で切替"],
              ] as const
            ).map(([k, lab]) => (
              <button
                key={k}
                type="button"
                className={`lp-chip${compare === k ? " active" : ""}`}
                onClick={() => setCompare(k)}
              >
                {lab}
              </button>
            ))}
            {compare === "toggle" ? (
              <button
                type="button"
                className={`lp-chip${showBefore ? " active" : ""}`}
                onClick={() => setShowBefore((v) => !v)}
              >
                {showBefore ? "変更前を表示中" : "変更後を表示中"}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      {compare === "stack" && previous ? (
        <>
          <h3 className="lp-subh">変更後（{current.versionKey}）</h3>
          <CenturyTable
            model={current}
            years={years}
            seriesFilter={seriesFilter}
            highlight={sig}
          />
          <h3 className="lp-subh">変更前（{previous.versionKey}）</h3>
          <CenturyTable model={previous} years={years} seriesFilter={seriesFilter} />
        </>
      ) : (
        <CenturyTable
          model={modelShown}
          years={years}
          seriesFilter={seriesFilter}
          highlight={sig}
          overlay={compare === "toggle" && !showBefore ? previous : null}
        />
      )}
    </>
  );
}
