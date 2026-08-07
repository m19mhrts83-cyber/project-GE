/** Quiet Edge — いびきスコア／回数の二重軸 SVG（依存ライブラリなし） */

export type SnorePoint = {
  date: string;
  score: number;
  count: number | null;
  event: string;
};

function isTreatment(event: string) {
  return event === "治療当日" || event === "治療直後";
}

export default function SnoreTrendChart({ points }: { points: SnorePoint[] }) {
  const data = points.filter((p) => p.date && Number.isFinite(p.score));
  if (data.length < 2) {
    return <p className="empty">グラフ用の日次が足りません</p>;
  }

  const w = 720;
  const h = 280;
  const padL = 44;
  const padR = 48;
  const padT = 18;
  const padB = 40;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  const scores = data.map((p) => p.score);
  const counts = data
    .map((p) => p.count)
    .filter((c): c is number => c != null && Number.isFinite(c));
  const minScore = Math.min(0, ...scores);
  const maxScore = Math.max(60, ...scores, 1);
  const minCount = 0;
  const maxCount = Math.max(200, ...counts, 1);

  const xAt = (i: number) =>
    padL + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW);
  const yScore = (v: number) =>
    padT + ((maxScore - v) / Math.max(1, maxScore - minScore)) * innerH;
  const yCount = (v: number) =>
    padT + ((maxCount - v) / Math.max(1, maxCount - minCount)) * innerH;

  const scorePath: string[] = [];
  const countPath: string[] = [];
  let countStarted = false;
  data.forEach((p, i) => {
    scorePath.push(
      `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yScore(p.score).toFixed(1)}`,
    );
    if (p.count == null) {
      countStarted = false;
      return;
    }
    countPath.push(
      `${countStarted ? "L" : "M"}${xAt(i).toFixed(1)},${yCount(p.count).toFixed(1)}`,
    );
    countStarted = true;
  });

  const labelStep = Math.max(1, Math.ceil(data.length / 8));

  return (
    <div className="qe-chart-wrap">
      <svg
        className="qe-chart"
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label="いびきスコアと検出回数の推移"
      >
        <path
          d={scorePath.join(" ")}
          fill="none"
          stroke="#b45309"
          strokeWidth={2.2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <path
          d={countPath.join(" ")}
          fill="none"
          stroke="#4338ca"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          strokeDasharray="4 3"
        />
        {data.map((p, i) => {
          const treat = isTreatment(p.event);
          return (
            <g key={p.date}>
              <circle
                cx={xAt(i)}
                cy={yScore(p.score)}
                r={treat ? 4.5 : 3}
                fill={treat ? "#e11d48" : "#b45309"}
              />
              {p.count != null ? (
                <circle
                  cx={xAt(i)}
                  cy={yCount(p.count)}
                  r={treat ? 4 : 2.5}
                  fill={treat ? "#059669" : "#4338ca"}
                />
              ) : null}
              {i % labelStep === 0 || i === data.length - 1 ? (
                <text
                  x={xAt(i)}
                  y={h - 12}
                  textAnchor="middle"
                  fontSize={9}
                  fill="#78716c"
                >
                  {p.date.slice(5)}
                </text>
              ) : null}
            </g>
          );
        })}
        <text x={4} y={padT + 8} fontSize={10} fill="#b45309">
          {Math.round(maxScore)}
        </text>
        <text x={4} y={h - padB} fontSize={10} fill="#b45309">
          {Math.round(minScore)}
        </text>
        <text x={w - 44} y={padT + 8} fontSize={10} fill="#4338ca">
          {Math.round(maxCount)}
        </text>
        <text x={w - 44} y={h - padB} fontSize={10} fill="#4338ca">
          0
        </text>
      </svg>
      <div className="qe-chart-legend" aria-hidden>
        <span>
          <i style={{ background: "#b45309" }} />
          スコア
        </span>
        <span>
          <i style={{ background: "#4338ca" }} />
          回数
        </span>
        <span>
          <i style={{ background: "#e11d48" }} />
          治療日スコア
        </span>
        <span>
          <i style={{ background: "#059669" }} />
          治療日回数
        </span>
      </div>
    </div>
  );
}
