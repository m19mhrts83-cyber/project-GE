"use client";

import { useMemo, useState } from "react";
import { fmtManUnit } from "@/lib/format";
import {
  decadesFromYears,
  defaultYearWindow,
  eventsForYear,
  notesForLine,
  planDeltasForLine,
  shinjiHorizon,
  significantDiffs,
  yearsWithActuals,
  type CenturyDiff,
  type CenturyLine,
  type CenturyModel,
  type LifeEventModel,
  type LifeplanNote,
  type LineDelta,
  type SeriesKind,
} from "@/lib/centuryPlan";

type CompareMode = "inline" | "latest" | "stack";
type SeriesFilter = "both" | "plan" | "actual";
type RangeKey = "all" | "near" | "to100" | "actuals" | number;

function Sparkline({
  years,
  plan,
  actual,
  nowYear,
  age100Year,
}: {
  years: number[];
  plan: (number | null)[];
  actual: (number | null)[];
  nowYear: number;
  age100Year: number | null;
}) {
  const pts = (vals: (number | null)[]) =>
    years
      .map((y, i) => ({ y, v: vals[i] }))
      .filter((p): p is { y: number; v: number } => p.v != null);
  const planPts = pts(plan);
  if (planPts.length < 2) return <p className="meta">グラフ用の計画値が足りません。</p>;
  const actualPts = pts(actual);
  const w = 720;
  const h = 150;
  const pad = 14;
  const vs = [...planPts, ...actualPts].map((p) => p.v);
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
  const poly = (list: { y: number; v: number }[]) =>
    list.map((p) => {
      const { x, y } = xy(p.y, p.v);
      return `${x},${y}`;
    }).join(" ");
  const zeroY = xy(x0, 0).y;
  const nowX = xy(nowYear, 0).x;
  const age100X = age100Year != null ? xy(age100Year, 0).x : null;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="lp-spark" role="img" aria-label="貯蓄可能額の推移（〜100歳）">
      <line x1={pad} x2={w - pad} y1={zeroY} y2={zeroY} className="lp-spark-zero" />
      <line x1={nowX} x2={nowX} y1={pad} y2={h - pad} className="lp-spark-now" />
      {age100X != null ? (
        <line x1={age100X} x2={age100X} y1={pad} y2={h - pad} className="lp-spark-100" />
      ) : null}
      <polyline fill="none" points={poly(planPts)} className="lp-spark-line plan" />
      {actualPts.length >= 2 ? (
        <polyline fill="none" points={poly(actualPts)} className="lp-spark-line actual" />
      ) : null}
    </svg>
  );
}

function DeltaMark({ d }: { d: LineDelta | undefined }) {
  if (!d || d.delta == null) return null;
  const up = d.delta > 0;
  return (
    <span
      className={`lp-delta ${up ? "up" : "down"}`}
      title={`前回 ${fmtManUnit(d.before)} → ${fmtManUnit(d.after)}`}
    >
      {up ? "▲" : "▼"}
      {fmtManUnit(Math.abs(d.delta)).replace("万", "")}
    </span>
  );
}

function YearHead({
  year,
  nowYear,
  age,
  age100Year,
  events,
}: {
  year: number;
  nowYear: number;
  age: number | null;
  age100Year: number | null;
  events: ReturnType<typeof eventsForYear>;
}) {
  const chips = events.slice(0, 3).map((e) => e.text);
  const extra = events.length - chips.length;
  const title = events.map((e) => `${e.source}: ${e.text}`).join("\n");
  const is100 = age === 100 || year === age100Year;
  const isNow = year === nowYear;
  return (
    <th
      className={`num th-year${isNow ? " year-now" : ""}${is100 ? " year-100" : ""}`}
      title={title || undefined}
    >
      <div className="y">{year}</div>
      {age != null ? <div className="age">{is100 ? "100歳" : `${age}歳`}</div> : <div className="age">&nbsp;</div>}
      <div className="ev">
        {chips.join(" · ")}
        {extra > 0 ? ` +${extra}` : ""}
      </div>
    </th>
  );
}

function CenturyTable({
  model,
  years,
  seriesFilter,
  overlay,
  showInlineDiff,
  events,
  notes,
  nowYear,
  age100Year,
  openNoteItem,
  onOpenNote,
}: {
  model: CenturyModel;
  years: number[];
  seriesFilter: SeriesFilter;
  overlay?: CenturyModel | null;
  showInlineDiff: boolean;
  events: LifeEventModel | null;
  notes: LifeplanNote[];
  nowYear: number;
  age100Year: number | null;
  openNoteItem: string | null;
  onOpenNote: (item: string) => void;
}) {
  const shinji = events?.people.find((p) => p.name === "真治");
  const sections: { key: CenturyLine["section"]; title: string }[] = [
    { key: "income", title: "生活収入" },
    { key: "expense", title: "生活支出" },
    { key: "eval", title: "収支評価（収入−支出）" },
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
            <th className="series-col">区分</th>
            {years.map((y) => (
              <YearHead
                key={y}
                year={y}
                nowYear={nowYear}
                age={shinji?.ages[y] ?? null}
                age100Year={age100Year}
                events={eventsForYear(events, y)}
              />
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
                showInlineDiff={showInlineDiff}
                notes={notes}
                openNoteItem={openNoteItem}
                onOpenNote={onOpenNote}
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
  showInlineDiff,
  notes,
  openNoteItem,
  onOpenNote,
}: {
  title: string;
  colSpan: number;
  rows: CenturyLine[];
  years: number[];
  overlay?: CenturyModel | null;
  showInlineDiff: boolean;
  notes: LifeplanNote[];
  openNoteItem: string | null;
  onOpenNote: (item: string) => void;
}) {
  return (
    <>
      <tr className="section-row">
        <td colSpan={colSpan}>{title}</td>
      </tr>
      {rows.map((row) => {
        const deltas = showInlineDiff ? planDeltasForLine(row, overlay ?? null) : {};
        const rowNotes = notesForLine(notes, row);
        const seriesCls = row.series === "plan" ? "row-plan" : "row-actual";
        return (
          <tr
            key={row.id}
            className={`${seriesCls}${row.isTotal ? " total-row" : ""}`}
          >
            <td className="sticky-col">
              <span className="item-lab">{row.label}</span>
              {rowNotes.length ? (
                <button
                  type="button"
                  className={`note-dot${openNoteItem && rowNotes.some((n) => n.item === openNoteItem) ? " active" : ""}`}
                  title={rowNotes.map((n) => n.body || n.item).join(" / ")}
                  onClick={() => onOpenNote(rowNotes[0].item)}
                >
                  注
                </button>
              ) : null}
            </td>
            <td>
              <span className={`series-pill ${row.series}`}>
                {row.series === "plan" ? "計画" : "実績"}
              </span>
            </td>
            {years.map((y) => {
              const cur = row.values[y] ?? null;
              const d = deltas[y];
              return (
                <td
                  key={y}
                  className={`num${d ? (d.delta! > 0 ? " diff-pos" : " diff-neg") : ""}`}
                >
                  <span className="cell-val">{fmtManUnit(cur)}</span>
                  <DeltaMark d={d} />
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}

function NotesPanel({
  notes,
  focusItem,
}: {
  notes: LifeplanNote[];
  focusItem: string | null;
}) {
  const checks = notes.filter((n) => n.kind === "check");
  const hist = notes.filter((n) => n.kind === "history");
  if (!notes.length) {
    return <p className="meta">Numbers に残っている要確認・変更履歴はありません。</p>;
  }
  const block = (title: string, rows: LifeplanNote[]) =>
    rows.length ? (
      <div className="lp-notes-block">
        <h3 className="lp-subh">{title}</h3>
        <ul className="lp-notes-list">
          {rows.map((n, i) => (
            <li
              key={`${n.kind}-${n.item}-${i}`}
              className={focusItem && n.item === focusItem ? "focus" : undefined}
            >
              <strong>{n.item || "（項目なし）"}</strong>
              {n.date ? <span className="meta"> {n.date}</span> : null}
              {n.body ? <div>{n.body}</div> : <div className="meta">本文なし</div>}
              {n.result ? <div className="meta">結果・備考: {n.result}</div> : null}
            </li>
          ))}
        </ul>
      </div>
    ) : null;
  return (
    <>
      {block("要確認事項（閲覧）", checks)}
      {block("主要変更履歴（閲覧）", hist)}
    </>
  );
}

export default function CenturyExplorer({
  current,
  previous,
  diffs,
  events,
  notes,
}: {
  current: CenturyModel;
  previous: CenturyModel | null;
  diffs: CenturyDiff[];
  events: LifeEventModel | null;
  notes: LifeplanNote[];
}) {
  const nowYear = new Date().getFullYear();
  const def = defaultYearWindow(nowYear);
  const decades = decadesFromYears(current.years);
  const horizon = shinjiHorizon(events, nowYear);
  const actualYears = yearsWithActuals(current);
  const [range, setRange] = useState<RangeKey>("all");
  const [seriesFilter, setSeriesFilter] = useState<SeriesFilter>("both");
  const [compare, setCompare] = useState<CompareMode>(previous ? "inline" : "latest");
  const [showNotes, setShowNotes] = useState(false);
  const [focusItem, setFocusItem] = useState<string | null>(null);

  const years = useMemo(() => {
    if (range === "all") return current.years;
    if (range === "near") {
      return current.years.filter((y) => y >= def.start && y <= def.end);
    }
    if (range === "to100") {
      const end = horizon.age100Year ?? current.years[current.years.length - 1];
      return current.years.filter((y) => y >= nowYear && y <= end);
    }
    if (range === "actuals") {
      if (!actualYears.length) return current.years.filter((y) => y >= nowYear - 2 && y <= nowYear);
      const start = actualYears[0];
      const end = Math.max(actualYears[actualYears.length - 1], nowYear);
      return current.years.filter((y) => y >= start && y <= end);
    }
    return current.years.filter((y) => y >= range && y < range + 10);
  }, [current.years, range, def.start, def.end, horizon.age100Year, nowYear, actualYears]);

  const sig = significantDiffs(diffs);
  const evalPlan = current.lines.find(
    (l) => l.section === "eval" && l.series === "plan" && l.label.includes("合計")
  );
  const evalActual = current.lines.find(
    (l) => l.section === "eval" && l.series === "actual" && l.label.includes("合計")
  );
  const sparkYears = current.years;
  const sparkPlan = sparkYears.map((y) => evalPlan?.values[y] ?? null);
  const sparkActual = sparkYears.map((y) => evalActual?.values[y] ?? null);
  const thisYear = evalPlan?.values[nowYear] ?? null;
  const overlay = compare === "inline" ? previous : null;

  const openNote = (item: string) => {
    setFocusItem(item);
    setShowNotes(true);
  };

  const age100Label =
    horizon.age100Year != null
      ? `${horizon.age100Year}年`
      : current.years.length
        ? `${current.years[current.years.length - 1]}年`
        : "—";

  return (
    <>
      <div className="grid" style={{ marginBottom: 16 }}>
        <article className="card">
          <header>
            <span className="lvl">100歳まで</span>
            <strong>
              真治 {horizon.nowAge != null ? `${horizon.nowAge}歳` : "—"}（{nowYear}）→ 100歳（
              {age100Label}）
            </strong>
          </header>
          <p className="meta" style={{ margin: "0 0 8px" }}>
            Numbers「表3.ライフイベント」とキャッシュフローを年で揃えています。単位は万円。
            {horizon.startYear && horizon.endYear
              ? ` 表示対象は ${horizon.startYear}〜${horizon.endYear}年。`
              : null}
          </p>
          <p style={{ margin: 0, fontSize: "1.35rem", fontWeight: 800 }}>
            {nowYear}年 貯蓄可能額（計画） {fmtManUnit(thisYear)}
          </p>
        </article>
        <article className="card">
          <header>
            <span className="lvl">推移</span>
            <strong>合計・貯蓄可能額（全期間）</strong>
          </header>
          <Sparkline
            years={sparkYears}
            plan={sparkPlan}
            actual={sparkActual}
            nowYear={nowYear}
            age100Year={horizon.age100Year}
          />
          <div className="lp-bar-legend meta" style={{ marginTop: 8 }}>
            <span className="swatch plan" /> 計画
            <span className="swatch actual" /> 実績
            <span>縦線＝今年 / 100歳</span>
          </div>
        </article>
      </div>

      {previous ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">計画の差分</span>
            <strong>
              前回 {previous.versionKey} → 今回 {current.versionKey}
            </strong>
          </header>
          <p className="meta" style={{ margin: "8px 0 0" }}>
            表の計画行は、前回から動いたセルを緑（増）／赤（減）で示します。▲▼は前回比（万円）。
          </p>
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
        <div className="lp-chips" aria-label="表示期間">
          <button
            type="button"
            className={`lp-chip${range === "all" ? " active" : ""}`}
            onClick={() => setRange("all")}
          >
            全期間
          </button>
          <button
            type="button"
            className={`lp-chip${range === "near" ? " active" : ""}`}
            onClick={() => setRange("near")}
          >
            過去2年〜先12年
          </button>
          <button
            type="button"
            className={`lp-chip${range === "actuals" ? " active" : ""}`}
            onClick={() => setRange("actuals")}
          >
            実績のある年
          </button>
          <button
            type="button"
            className={`lp-chip${range === "to100" ? " active" : ""}`}
            onClick={() => setRange("to100")}
          >
            これから〜100歳
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
                ["inline", "行内で差分"],
                ["latest", "最新のみ"],
                ["stack", "上下に並べる"],
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
          </div>
        ) : null}
        <div className="lp-chips">
          <button
            type="button"
            className={`lp-chip${showNotes ? " active" : ""}`}
            onClick={() => setShowNotes((v) => !v)}
          >
            コメント・要確認（{notes.length}）
          </button>
        </div>
      </div>

      <p className="lp-legend-inline meta">
        <span className="series-pill plan">計画</span>
        インク紺　
        <span className="series-pill actual">実績</span>
        オレンジ　年ヘッダは真治の年齢＋ライフイベント。編集は Numbers 側です。
      </p>

      {showNotes ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">閲覧専用</span>
            <strong>Numbers に入っていたコメント</strong>
          </header>
          <NotesPanel notes={notes} focusItem={focusItem} />
        </div>
      ) : null}

      {compare === "stack" && previous ? (
        <>
          <h3 className="lp-subh">変更後（{current.versionKey}）</h3>
          <CenturyTable
            model={current}
            years={years}
            seriesFilter={seriesFilter}
            overlay={previous}
            showInlineDiff
            events={events}
            notes={notes}
            nowYear={nowYear}
            age100Year={horizon.age100Year}
            openNoteItem={focusItem}
            onOpenNote={openNote}
          />
          <h3 className="lp-subh">変更前（{previous.versionKey}）</h3>
          <CenturyTable
            model={previous}
            years={years}
            seriesFilter={seriesFilter}
            showInlineDiff={false}
            events={events}
            notes={notes}
            nowYear={nowYear}
            age100Year={horizon.age100Year}
            openNoteItem={focusItem}
            onOpenNote={openNote}
          />
        </>
      ) : (
        <CenturyTable
          model={current}
          years={years}
          seriesFilter={seriesFilter}
          overlay={overlay}
          showInlineDiff={compare === "inline"}
          events={events}
          notes={notes}
          nowYear={nowYear}
          age100Year={horizon.age100Year}
          openNoteItem={focusItem}
          onOpenNote={openNote}
        />
      )}
    </>
  );
}
