import type { GluconTrendPoint } from "@/lib/glucon/stats";

const COLOR_ACTIVITY = "#4338ca";
const COLOR_RESULT = "#0f766e";
const COLOR_POINTS = "#b45309";
const COLOR_CUMULATIVE = "#7c3aed";
const COLOR_GRID = "#e7e5e4";

function niceStep(span: number, targetTicks: number): number {
  if (span <= 0) return 1;
  const raw = span / Math.max(1, targetTicks);
  const pow = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / pow;
  const nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return nice * pow;
}

function ticks(min: number, max: number, targetTicks = 4): number[] {
  const step = niceStep(max - min, targetTicks);
  const start = Math.ceil(min / step) * step;
  const out: number[] = [];
  for (let v = start; v <= max + step * 1e-9; v += step) {
    out.push(Math.round(v * 1000) / 1000);
  }
  if (!out.includes(min)) out.unshift(min);
  if (!out.includes(max)) out.push(max);
  return [...new Set(out)].sort((a, b) => a - b);
}

export default function GluconTrendChart({
  points,
  mode,
}: {
  points: GluconTrendPoint[];
  mode: "frequency" | "points";
}) {
  const data = points.filter((p) => p.periodKey);
  if (!data.length) return null;

  const w = 760;
  const h = 240;
  const padL = 44;
  const padR = mode === "points" ? 52 : 16;
  const padT = 20;
  const padB = 36;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const n = data.length;
  const groupW = innerW / Math.max(1, n);
  const xCenter = (i: number) => padL + groupW * i + groupW / 2;

  const maxLeft =
    mode === "frequency"
      ? Math.max(1, ...data.map((p) => p.activityPosted + p.resultPosted), 2)
      : Math.max(1, ...data.map((p) => p.points));
  const maxRight = Math.max(1, ...data.map((p) => p.cumulativePoints));
  const leftTicks = ticks(0, maxLeft, 4);
  const rightTicks = ticks(0, maxRight, 4);
  const yLeft = (v: number) =>
    padT + ((maxLeft - v) / Math.max(1, maxLeft)) * innerH;
  const yRight = (v: number) =>
    padT + ((maxRight - v) / Math.max(1, maxRight)) * innerH;

  const labelStep = Math.max(1, Math.ceil(n / 8));
  const title =
    mode === "frequency"
      ? "月次の報告回数（活動投稿・成果投稿）"
      : "月次の神大家ポイント目安と累計";
  const aria =
    mode === "frequency"
      ? "グルコン報告の月次投稿回数"
      : "グルコン成果の目安ポイント推移";

  const linePath = data
    .map((p, i) => {
      const cmd = i === 0 ? "M" : "L";
      return `${cmd}${xCenter(i).toFixed(1)},${yRight(p.cumulativePoints).toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="qe-chart-wrap glucon-chart-wrap">
      <p className="meta glucon-chart-title">{title}</p>
      <svg
        className="qe-chart"
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label={aria}
      >
        {leftTicks.map((v) => {
          const y = yLeft(v);
          return (
            <g key={`lg-${v}`}>
              <line
                x1={padL}
                x2={w - padR}
                y1={y}
                y2={y}
                stroke={COLOR_GRID}
                strokeWidth={1}
              />
              <text
                x={padL - 6}
                y={y + 3}
                textAnchor="end"
                fontSize={10}
                fill="#57534e"
              >
                {Number.isInteger(v) ? v : v.toFixed(1)}
              </text>
            </g>
          );
        })}
        {mode === "points"
          ? rightTicks.map((v) => (
              <text
                key={`rg-${v}`}
                x={w - padR + 6}
                y={yRight(v) + 3}
                textAnchor="start"
                fontSize={10}
                fill={COLOR_CUMULATIVE}
              >
                {Number.isInteger(v) ? v : v.toFixed(0)}
              </text>
            ))
          : null}

        {data.map((p, i) => {
          const cx = xCenter(i);
          if (mode === "frequency") {
            const barW = Math.min(14, groupW * 0.28);
            const gap = 3;
            const aH = innerH - (yLeft(p.activityPosted) - padT);
            const rH = innerH - (yLeft(p.resultPosted) - padT);
            return (
              <g key={p.periodKey}>
                <rect
                  x={cx - barW - gap / 2}
                  y={yLeft(p.activityPosted)}
                  width={barW}
                  height={Math.max(0, aH)}
                  fill={COLOR_ACTIVITY}
                />
                <rect
                  x={cx + gap / 2}
                  y={yLeft(p.resultPosted)}
                  width={barW}
                  height={Math.max(0, rH)}
                  fill={COLOR_RESULT}
                />
              </g>
            );
          }
          const barW = Math.min(22, groupW * 0.45);
          const pH = innerH - (yLeft(p.points) - padT);
          return (
            <rect
              key={p.periodKey}
              x={cx - barW / 2}
              y={yLeft(p.points)}
              width={barW}
              height={Math.max(0, pH)}
              fill={COLOR_POINTS}
            />
          );
        })}

        {mode === "points" ? (
          <>
            <path
              d={linePath}
              fill="none"
              stroke={COLOR_CUMULATIVE}
              strokeWidth={2}
            />
            {data.map((p, i) => (
              <circle
                key={`c-${p.periodKey}`}
                cx={xCenter(i)}
                cy={yRight(p.cumulativePoints)}
                r={3}
                fill={COLOR_CUMULATIVE}
              />
            ))}
          </>
        ) : null}

        {data.map((p, i) =>
          i % labelStep === 0 || i === n - 1 ? (
            <text
              key={`x-${p.periodKey}`}
              x={xCenter(i)}
              y={h - 12}
              textAnchor="middle"
              fontSize={10}
              fill="#57534e"
            >
              {p.periodKey.slice(2)}
            </text>
          ) : null,
        )}
      </svg>
      <p className="meta">
        {mode === "frequency"
          ? "左軸: 件数（0/1）／ 藍=活動投稿 ／ 緑=成果投稿"
          : "左軸: 当月の目安点 ／ 右軸: 累計（紫）"}
      </p>
    </div>
  );
}
