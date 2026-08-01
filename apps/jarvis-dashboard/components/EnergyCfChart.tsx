/** 電力・太陽光 CF の簡易 SVG グラフ（依存ライブラリなし） */

export type EnergyPoint = {
  ym: string;
  buy: number | null;
  sell: number | null;
  loan: number | null;
  net: number | null;
};

export default function EnergyCfChart({ points }: { points: EnergyPoint[] }) {
  const data = points.filter((p) => p.ym);
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
    <div className="energy-chart-wrap">
      <svg
        className="energy-chart"
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label="太陽光キャッシュフロー推移（買電・売電・ネット）"
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
    </div>
  );
}
