 "use client";

import { useState } from "react";
import { fmtYen, fmtYenSigned } from "@/lib/format";
import type { HouseholdBsTrendRow } from "@/lib/householdBsInsights";

function miniAmount(n: number): string {
  const man = Math.round(n / 10_000);
  return `${man.toLocaleString("ja-JP")}万`;
}

type LineKey =
  | "incomeJpy"
  | "expenseJpy"
  | "cashExpenseJpy"
  | "cashflowAfterDebtJpy"
  | "cashJpy"
  | "netWorthJpy"
  | "liabilityJpy";

function LineChartView({
  rows,
  series,
  ariaLabel,
  note,
}: {
  rows: HouseholdBsTrendRow[];
  series: Array<{
    key: LineKey;
    label: string;
    color: string;
    dash?: boolean;
    showLabel?: boolean;
  }>;
  ariaLabel: string;
  note?: string;
}) {
  const [tip, setTip] = useState<{
    x: number;
    y: number;
    title: string;
    value: string;
    meta: string;
  } | null>(null);
  if (rows.length < 2) return <p className="meta">推移データが足りません。</p>;
  const w = 980;
  const h = 280;
  const pad = 42;
  const years = rows.map((r) => r.year);
  const values = rows.flatMap((r) => series.map((s) => r[s.key]));
  const min = Math.min(0, ...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x0 = years[0];
  const x1 = years[years.length - 1];
  const xspan = x1 - x0 || 1;
  const xy = (year: number, v: number) => {
    const x = pad + ((year - x0) / xspan) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return { x, y };
  };
  return (
    <div style={{ position: "relative" }}>
      {note ? (
        <p className="meta" style={{ margin: "0 0 10px" }}>
          {note}
        </p>
      ) : null}
      <svg
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label={ariaLabel}
        style={{ width: "100%", maxWidth: w, height: "auto" }}
        onMouseLeave={() => setTip(null)}
      >
        <line
          x1={pad}
          x2={w - pad}
          y1={xy(x0, 0).y}
          y2={xy(x0, 0).y}
          stroke="var(--border, #ccc)"
          strokeWidth={1}
        />
        {[max, (max + min) / 2, min].map((tick, idx) => {
          const y = xy(x0, tick).y;
          return (
            <g key={`${tick}-${idx}`}>
              <line
                x1={pad}
                x2={w - pad}
                y1={y}
                y2={y}
                stroke="var(--border, #e4e4e4)"
                strokeWidth={1}
                strokeDasharray="3 4"
              />
              <text x={4} y={y + 4} fontSize={12} fill="var(--muted, #666)">
                {miniAmount(tick)}
              </text>
            </g>
          );
        })}
        {series.map((s) => {
          const points = rows.map((r) => {
            const p = xy(r.year, r[s.key]);
            return `${p.x},${p.y}`;
          });
          return (
            <polyline
              key={s.key}
              fill="none"
              points={points.join(" ")}
              stroke={s.color}
              strokeWidth={3}
              strokeDasharray={s.dash ? "8 6" : undefined}
              opacity={0.9}
            />
          );
        })}
        {rows.map((r) => {
          const x = xy(r.year, 0).x;
          return (
            <text
              key={`year-${r.year}`}
              x={x - 12}
              y={h - 10}
              fontSize={12}
              fill="var(--muted, #666)"
            >
              {r.year}
            </text>
          );
        })}
        {series.flatMap((s) =>
          rows.map((r) => {
            const p = xy(r.year, r[s.key]);
            return (
              <g key={`${s.key}-${r.year}`}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={10}
                  fill="transparent"
                  style={{ cursor: "pointer" }}
                  onMouseEnter={() =>
                    setTip({
                      x: p.x,
                      y: p.y,
                      title: `${r.year}年 ${s.label}`,
                      value: fmtYen(r[s.key]),
                      meta: r.estimated
                        ? "推定・補完年"
                        : r.snapshotAsOf
                          ? `実績スナップ ${r.snapshotAsOf}`
                          : "実績",
                    })
                  }
                  onFocus={() =>
                    setTip({
                      x: p.x,
                      y: p.y,
                      title: `${r.year}年 ${s.label}`,
                      value: fmtYen(r[s.key]),
                      meta: r.estimated
                        ? "推定・補完年"
                        : r.snapshotAsOf
                          ? `実績スナップ ${r.snapshotAsOf}`
                          : "実績",
                    })
                  }
                />
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={r.estimated ? 4.2 : 5}
                  fill={r.estimated ? "#fff" : s.color}
                  stroke={s.color}
                  strokeWidth={r.estimated ? 2 : 1.6}
                  opacity={r.estimated ? 0.55 : 1}
                />
                {s.showLabel ? (
                  <text
                    x={p.x + 6}
                    y={p.y - 6}
                    fontSize={r.estimated ? 10 : 11}
                    fill={s.color}
                    opacity={r.estimated ? 0.55 : 0.92}
                  >
                    {miniAmount(r[s.key])}
                  </text>
                ) : null}
              </g>
            );
          })
        )}
      </svg>
      {tip ? (
        <div
          style={{
            position: "absolute",
            left: `clamp(8px, calc(${((tip.x / w) * 100).toFixed(2)}% + 10px), calc(100% - 220px))`,
            top: `clamp(8px, calc(${((tip.y / h) * 100).toFixed(2)}% - 8px), calc(100% - 84px))`,
            background: "rgba(28,25,23,0.94)",
            color: "#fafaf9",
            borderRadius: 10,
            padding: "8px 10px",
            fontSize: 12,
            lineHeight: 1.45,
            pointerEvents: "none",
            boxShadow: "0 8px 24px rgba(28,25,23,0.16)",
          }}
        >
          <div style={{ fontWeight: 700 }}>{tip.title}</div>
          <div>{tip.value}</div>
          <div style={{ opacity: 0.82 }}>{tip.meta}</div>
        </div>
      ) : null}
      <div
        className="meta"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "8px 18px",
          marginTop: 10,
        }}
      >
        {series.map((s) => (
          <span key={s.key} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                width: 18,
                height: 0,
                borderTop: `3px ${s.dash ? "dashed" : "solid"} ${s.color}`,
                display: "inline-block",
              }}
            />
            {s.label}
          </span>
        ))}
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: "#999",
              opacity: 0.3,
              display: "inline-block",
            }}
          />
          推定・補完年
        </span>
      </div>
    </div>
  );
}

export default function HouseholdBsTrendPanel({
  rows,
}: {
  rows: HouseholdBsTrendRow[];
}) {
  const sorted = [...rows].sort((a, b) => a.year - b.year);
  const current = sorted[sorted.length - 1] ?? null;
  const prev = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  return (
    <div style={{ marginTop: 12 }}>
      <div className="card">
        <header>
          <span className="lvl">年次推移</span>
          <strong>大きいレンジで見るキャッシュの推移</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          過去推移は年次スナップ基準です。横軸が年、縦軸が金額です。点にカーソルを乗せると各年の金額を確認できます。薄い点は年次スナップが無く、その年の材料から補完した推定値です。
          {current && prev
            ? ` 直近は ${current.year}年、前年差は純資産 ${fmtYenSigned(
                current.netWorthJpy - prev.netWorthJpy
              )} / 負債 ${fmtYenSigned(current.liabilityJpy - prev.liabilityJpy)}。`
            : ""}
        </p>
      </div>

      <article className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">フロー</span>
          <strong>収入・返済込みキャッシュ支出・返済後キャッシュ収支</strong>
        </header>
        <LineChartView
          rows={sorted}
          series={[
            { key: "incomeJpy", label: "収入", color: "#2e7d32", showLabel: true },
            { key: "expenseJpy", label: "会計上の支出", color: "#ef6c00", dash: true },
            { key: "cashExpenseJpy", label: "返済込みキャッシュ支出", color: "#c62828", showLabel: true },
            { key: "cashflowAfterDebtJpy", label: "返済後キャッシュ収支", color: "#1565c0", showLabel: true },
          ]}
          ariaLabel="収入と返済込みキャッシュ収支の推移"
          note="赤はローン元本返済を含む実際のキャッシュ流出です。青がプラスで積み上がるほど、Cash is King の土台が厚くなります。"
        />
      </article>

      <article className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">土台</span>
          <strong>キャッシュ残高・純資産・負債残高</strong>
        </header>
        <LineChartView
          rows={sorted}
          series={[
            { key: "cashJpy", label: "キャッシュ残高", color: "#0d47a1", showLabel: true },
            { key: "netWorthJpy", label: "純資産", color: "#2e7d32", showLabel: true },
            { key: "liabilityJpy", label: "負債残高", color: "#8e24aa" },
          ]}
          ariaLabel="キャッシュ残高と純資産の推移"
          note="青は手元資金の厚み、緑は積み上がった純資産、紫は負債残高です。純資産が増え、負債が下がり、キャッシュが薄くなりすぎない流れが理想です。"
        />
      </article>
    </div>
  );
}
