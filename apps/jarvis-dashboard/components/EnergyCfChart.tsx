"use client";

/** 電力・太陽光 CF の簡易 SVG グラフ（依存ライブラリなし） */

import { useState } from "react";

export type EnergyPoint = {
  ym: string;
  buy: number | null;
  sell: number | null;
  loan: number | null;
  net: number | null;
};

function fmtValue(v: number | null): string {
  return v == null ? "—" : `${Math.round(v).toLocaleString("ja-JP")}円`;
}

export default function EnergyCfChart({ points }: { points: EnergyPoint[] }) {
  const data = points.filter((p) => p.ym);
  const [tip, setTip] = useState<{
    x: number;
    y: number;
    title: string;
    lines: string[];
  } | null>(null);
  if (data.length < 2) {
    return <p className="empty">グラフ用の月次が足りません</p>;
  }

  const w = 720;
  const h = 260;
  const padL = 52;
  const padR = 16;
  const padT = 18;
  const padB = 36;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  const vals = data.flatMap((p) =>
    [p.buy, p.sell, p.net].filter((x): x is number => x != null && !Number.isNaN(x)),
  );
  const minY = Math.min(0, ...vals);
  const maxY = Math.max(0, ...vals, 1);
  const span = Math.max(1, maxY - minY);

  const xAt = (i: number) =>
    padL + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW);
  const yAt = (v: number) => padT + ((maxY - v) / span) * innerH;

  const pathFor = (key: "buy" | "sell" | "net") => {
    const parts: string[] = [];
    let started = false;
    data.forEach((p, i) => {
      const v = p[key];
      if (v == null) {
        started = false;
        return;
      }
      parts.push(
        `${started ? "L" : "M"}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`,
      );
      started = true;
    });
    return parts.join(" ");
  };

  const zeroY = yAt(0);

  return (
    <div className="energy-chart-wrap" style={{ position: "relative" }}>
      <svg
        className="energy-chart"
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label="太陽光キャッシュフロー推移（買電・売電・ネット）"
        onMouseLeave={() => setTip(null)}
      >
        <line
          x1={padL}
          x2={w - padR}
          y1={zeroY}
          y2={zeroY}
          stroke="#d6d3d1"
          strokeDasharray="4 4"
        />
        <path
          d={pathFor("buy")}
          fill="none"
          stroke="#b45309"
          strokeWidth={2.2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <path
          d={pathFor("sell")}
          fill="none"
          stroke="#0f766e"
          strokeWidth={2.2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <path
          d={pathFor("net")}
          fill="none"
          stroke="#1d4ed8"
          strokeWidth={2.4}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {data.flatMap((p, i) =>
          [
            { key: "buy" as const, label: "買電", color: "#b45309" },
            { key: "sell" as const, label: "売電", color: "#0f766e" },
            { key: "net" as const, label: "ネットCF", color: "#1d4ed8" },
          ].flatMap((s) => {
            const v = p[s.key];
            if (v == null) return [];
            const x = xAt(i);
            const y = yAt(v);
            return [
              <g key={`${p.ym}-${s.key}`}>
                <circle
                  cx={x}
                  cy={y}
                  r={4.2}
                  fill={s.color}
                  stroke="#fff"
                  strokeWidth={1.4}
                />
                <circle
                  cx={x}
                  cy={y}
                  r={10}
                  fill="transparent"
                  style={{ cursor: "pointer" }}
                  onMouseEnter={() =>
                    setTip({
                      x,
                      y,
                      title: `${p.ym} ${s.label}`,
                      lines: [
                        `${s.label}: ${fmtValue(v)}`,
                        `買電: ${fmtValue(p.buy)}`,
                        `売電: ${fmtValue(p.sell)}`,
                        `ローン: ${fmtValue(p.loan)}`,
                        `ネットCF: ${fmtValue(p.net)}`,
                      ],
                    })
                  }
                  onFocus={() =>
                    setTip({
                      x,
                      y,
                      title: `${p.ym} ${s.label}`,
                      lines: [
                        `${s.label}: ${fmtValue(v)}`,
                        `買電: ${fmtValue(p.buy)}`,
                        `売電: ${fmtValue(p.sell)}`,
                        `ローン: ${fmtValue(p.loan)}`,
                        `ネットCF: ${fmtValue(p.net)}`,
                      ],
                    })
                  }
                />
              </g>,
            ];
          }),
        )}
        {data.map((p, i) => (
          <text
            key={p.ym}
            x={xAt(i)}
            y={h - 10}
            textAnchor="middle"
            fontSize={10}
            fill="#78716c"
          >
            {p.ym.slice(2)}
          </text>
        ))}
        <text x={4} y={padT + 8} fontSize={10} fill="#78716c">
          {Math.round(maxY).toLocaleString("ja-JP")}
        </text>
        <text x={4} y={h - padB} fontSize={10} fill="#78716c">
          {Math.round(minY).toLocaleString("ja-JP")}
        </text>
      </svg>
      <div className="energy-chart-legend" aria-hidden>
        <span>
          <i style={{ background: "#b45309" }} />
          買電
        </span>
        <span>
          <i style={{ background: "#0f766e" }} />
          売電
        </span>
        <span>
          <i style={{ background: "#1d4ed8" }} />
          ネットCF
        </span>
      </div>
      {tip ? (
        <div
          style={{
            position: "absolute",
            left: `clamp(8px, calc(${((tip.x / w) * 100).toFixed(2)}% + 10px), calc(100% - 220px))`,
            top: `clamp(8px, calc(${((tip.y / h) * 100).toFixed(2)}% - 8px), calc(100% - 120px))`,
            minWidth: 170,
            maxWidth: 220,
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
