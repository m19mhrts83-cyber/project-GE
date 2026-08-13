"use client";

export type OverlaySeries = {
  key: string;
  label: string;
  values: (number | null)[];
  /** 強調（現行計画など） */
  emphasis?: boolean;
};

export default function OverlayLineChart({
  years,
  series,
  goalYen,
  markers = [],
  ariaLabel = "年次キャッシュフロー推移",
}: {
  years: number[];
  series: OverlaySeries[];
  goalYen?: number | null;
  markers?: { year: number; label: string }[];
  ariaLabel?: string;
}) {
  const pts = series.flatMap((s) =>
    years
      .map((y, i) => ({ y, v: s.values[i] }))
      .filter((p): p is { y: number; v: number } => p.v != null)
  );
  if (goalYen != null) {
    pts.push({ y: years[0] ?? 0, v: goalYen });
    pts.push({ y: years[years.length - 1] ?? 0, v: goalYen });
  }
  if (pts.length < 2 || years.length < 2) {
    return <p className="meta">重ねる値が足りません。</p>;
  }

  const w = 760;
  const h = 240;
  const pad = 28;
  const vs = pts.map((p) => p.v);
  const min = Math.min(0, ...vs);
  const max = Math.max(...vs, goalYen ?? 0);
  const span = max - min || 1;
  const x0 = years[0];
  const x1 = years[years.length - 1];
  const xspan = x1 - x0 || 1;
  const xy = (year: number, v: number) => {
    const x = pad + ((year - x0) / xspan) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return { x, y };
  };
  const colors = ["#0d47a1", "#6a1b9a", "#2e7d32", "#c62828", "#546e7a"];

  return (
    <div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label={ariaLabel}
        style={{ width: "100%", maxWidth: w, height: "auto" }}
      >
        <line
          x1={pad}
          x2={w - pad}
          y1={xy(x0, 0).y}
          y2={xy(x0, 0).y}
          stroke="var(--border, #ccc)"
          strokeWidth={1}
        />
        {goalYen != null ? (
          <line
            x1={pad}
            x2={w - pad}
            y1={xy(x0, goalYen).y}
            y2={xy(x1, goalYen).y}
            stroke="#c45c26"
            strokeWidth={1.5}
            strokeDasharray="6 4"
          />
        ) : null}
        {markers.map((m) => {
          const x = xy(m.year, 0).x;
          return (
            <g key={`${m.year}-${m.label}`}>
              <line
                x1={x}
                x2={x}
                y1={pad}
                y2={h - pad}
                stroke="var(--border, #bbb)"
                strokeDasharray="2 3"
              />
              <text
                x={x + 3}
                y={pad + 10}
                fontSize={10}
                fill="var(--muted, #666)"
              >
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
          const points = list
            .map((p) => {
              const { x, y } = xy(p.y, p.v);
              return `${x},${y}`;
            })
            .join(" ");
          return (
            <polyline
              key={s.key}
              fill="none"
              points={points}
              stroke={colors[i % colors.length]}
              strokeWidth={s.emphasis ? 2.8 : 1.8}
              opacity={s.emphasis ? 1 : 0.85}
            />
          );
        })}
        <text x={pad} y={14} fontSize={10} fill="var(--muted, #666)">
          {Math.round(max).toLocaleString("ja-JP")}
        </text>
        <text
          x={pad}
          y={h - 8}
          fontSize={10}
          fill="var(--muted, #666)"
        >
          {Math.round(min).toLocaleString("ja-JP")}
        </text>
      </svg>
      <ul
        className="meta"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "8px 16px",
          listStyle: "none",
          padding: 0,
          marginTop: 8,
        }}
      >
        {series.map((s, i) => (
          <li key={s.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                width: 14,
                height: 3,
                background: colors[i % colors.length],
                display: "inline-block",
              }}
            />
            {s.label}
          </li>
        ))}
        {goalYen != null ? (
          <li style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                width: 14,
                height: 0,
                borderTop: "2px dashed #c45c26",
                display: "inline-block",
              }}
            />
            目標 CF 月50万
          </li>
        ) : null}
      </ul>
    </div>
  );
}
