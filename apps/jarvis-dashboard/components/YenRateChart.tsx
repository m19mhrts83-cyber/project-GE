"use client";

/** USD/JPY 簡易 SVG グラフ（依存ライブラリなし） */

import { useState } from "react";

export type YenPoint = {
  trade_date: string;
  close: number;
};

function fmtPx(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v.toFixed(2)}`;
}

export default function YenRateChart({
  points,
  label = "USD/JPY",
}: {
  points: YenPoint[];
  label?: string;
}) {
  const data = points.filter((p) => p.trade_date && Number.isFinite(p.close));
  const [tip, setTip] = useState<{
    x: number;
    y: number;
    title: string;
    lines: string[];
  } | null>(null);

  if (data.length < 2) {
    return <p className="empty">グラフ用のレートが足りません</p>;
  }

  const w = 720;
  const h = 240;
  const padL = 48;
  const padR = 16;
  const padT = 16;
  const padB = 36;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  const vals = data.map((p) => p.close);
  const minY = Math.min(...vals);
  const maxY = Math.max(...vals);
  const span = Math.max(0.01, maxY - minY);
  const padY = span * 0.08;
  const yMin = minY - padY;
  const yMax = maxY + padY;
  const ySpan = yMax - yMin;

  const xAt = (i: number) =>
    padL + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW);
  const yAt = (v: number) => padT + ((yMax - v) / ySpan) * innerH;

  const path = data
    .map((p, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(p.close).toFixed(1)}`)
    .join(" ");

  const hi = Math.max(...vals);
  const lo = Math.min(...vals);
  const hiI = vals.indexOf(hi);
  const loI = vals.indexOf(lo);
  const labelStep = Math.max(1, Math.floor(data.length / 6));

  return (
    <div className="energy-chart-wrap" style={{ position: "relative" }}>
      <svg
        className="energy-chart"
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label={`${label} 推移`}
        onMouseLeave={() => setTip(null)}
      >
        <path
          d={path}
          fill="none"
          stroke="#1d4ed8"
          strokeWidth={2.2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <circle
          cx={xAt(hiI)}
          cy={yAt(hi)}
          r={4.5}
          fill="#b91c1c"
          stroke="#fff"
          strokeWidth={1.2}
        />
        <circle
          cx={xAt(loI)}
          cy={yAt(lo)}
          r={4.5}
          fill="#15803d"
          stroke="#fff"
          strokeWidth={1.2}
        />
        {data.map((p, i) => {
          const x = xAt(i);
          const y = yAt(p.close);
          return (
            <circle
              key={p.trade_date}
              cx={x}
              cy={y}
              r={10}
              fill="transparent"
              style={{ cursor: "pointer" }}
              onMouseEnter={() =>
                setTip({
                  x,
                  y,
                  title: p.trade_date,
                  lines: [`終値: ${fmtPx(p.close)} 円`],
                })
              }
            />
          );
        })}
        {data.map((p, i) =>
          i % labelStep === 0 || i === data.length - 1 ? (
            <text
              key={`lbl-${p.trade_date}`}
              x={xAt(i)}
              y={h - 10}
              textAnchor="middle"
              fontSize={10}
              fill="#78716c"
            >
              {p.trade_date.slice(5)}
            </text>
          ) : null,
        )}
        <text x={4} y={padT + 8} fontSize={10} fill="#78716c">
          {fmtPx(yMax)}
        </text>
        <text x={4} y={h - padB} fontSize={10} fill="#78716c">
          {fmtPx(yMin)}
        </text>
      </svg>
      <div className="energy-chart-legend" aria-hidden>
        <span>
          <i style={{ background: "#1d4ed8" }} />
          {label}
        </span>
        <span>
          <i style={{ background: "#b91c1c" }} />
          高 {fmtPx(hi)}
        </span>
        <span>
          <i style={{ background: "#15803d" }} />
          安 {fmtPx(lo)}
        </span>
      </div>
      {tip ? (
        <div
          style={{
            position: "absolute",
            left: `clamp(8px, calc(${((tip.x / w) * 100).toFixed(2)}% + 10px), calc(100% - 180px))`,
            top: `clamp(8px, calc(${((tip.y / h) * 100).toFixed(2)}% - 8px), calc(100% - 80px))`,
            minWidth: 140,
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
          <div style={{ fontWeight: 700, marginBottom: 4 }}>{tip.title}</div>
          {tip.lines.map((line, idx) => (
            <div key={`${tip.title}-${idx}`}>{line}</div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
