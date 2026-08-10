/** オプチャ【スレッド】日次追記の簡易 SVG 棒グラフ */

export type OpenchatDayPoint = {
  date: string;
  total: number;
  routes?: Record<string, number>;
};

export default function OpenchatThreadChart({
  points,
}: {
  points: OpenchatDayPoint[];
}) {
  const data = points.filter((p) => p.date);
  if (!data.length) {
    return <p className="empty">グラフ用の日次データがありません</p>;
  }

  const w = 720;
  const h = 220;
  const padL = 36;
  const padR = 12;
  const padT = 16;
  const padB = 36;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const maxY = Math.max(1, ...data.map((p) => p.total || 0));
  const barGap = 2;
  const barW = Math.max(2, innerW / data.length - barGap);

  const xAt = (i: number) => padL + i * (barW + barGap) + barW / 2;
  const yAt = (v: number) => padT + ((maxY - v) / maxY) * innerH;
  const zeroY = padT + innerH;

  const tickIdx = new Set<number>();
  if (data.length <= 10) {
    data.forEach((_, i) => tickIdx.add(i));
  } else {
    tickIdx.add(0);
    tickIdx.add(data.length - 1);
    tickIdx.add(Math.floor(data.length / 2));
    tickIdx.add(Math.floor(data.length / 4));
    tickIdx.add(Math.floor((3 * data.length) / 4));
  }

  return (
    <div className="openchat-chart-wrap">
      <svg
        className="openchat-chart"
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label="直近30日の【スレッド】追記件数"
      >
        {[0, 0.5, 1].map((t) => {
          const y = yAt(maxY * t);
          return (
            <line
              key={t}
              x1={padL}
              x2={w - padR}
              y1={y}
              y2={y}
              stroke="#e7e5e4"
              strokeDasharray="3 3"
            />
          );
        })}
        {data.map((p, i) => {
          const v = p.total || 0;
          const barH = zeroY - yAt(v);
          return (
            <rect
              key={p.date}
              x={xAt(i) - barW / 2}
              y={yAt(v)}
              width={barW}
              height={Math.max(0, barH)}
              rx={1.5}
              fill={v > 0 ? "#2563eb" : "#e7e5e4"}
            >
              <title>
                {p.date}: {v}件
              </title>
            </rect>
          );
        })}
        {data.map((p, i) =>
          tickIdx.has(i) ? (
            <text
              key={`t-${p.date}`}
              x={xAt(i)}
              y={h - 10}
              textAnchor="middle"
              fontSize={10}
              fill="#78716c"
            >
              {p.date.slice(5)}
            </text>
          ) : null,
        )}
        <text x={4} y={padT + 4} fontSize={10} fill="#78716c">
          {maxY}
        </text>
      </svg>
      <p className="meta" style={{ marginTop: 4 }}>
        青棒＝その日の【スレッド】追記合計（全ルート）
      </p>
    </div>
  );
}
