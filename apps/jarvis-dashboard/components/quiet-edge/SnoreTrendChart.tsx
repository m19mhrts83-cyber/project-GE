/** Quiet Edge — いびきスコア／いびき回数の二重軸 SVG */

import { SNORE_SCORE_TARGET } from "@/lib/quietEdgeContext";

export type SnorePoint = {
  date: string;
  score: number;
  count: number | null;
  event: string;
};

export { SNORE_SCORE_TARGET };

const COLOR_SCORE = "#b45309";
const COLOR_COUNT = "#4338ca";
const COLOR_TARGET = "#0f766e";
const COLOR_GRID = "#e7e5e4";

function isTreatment(event: string) {
  return event === "治療当日" || event === "治療直後";
}

function niceStep(span: number, targetTicks: number): number {
  if (span <= 0) return 1;
  const raw = span / Math.max(1, targetTicks);
  const pow = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / pow;
  const nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return nice * pow;
}

function ticks(min: number, max: number, targetTicks = 5): number[] {
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

export default function SnoreTrendChart({ points }: { points: SnorePoint[] }) {
  const data = points.filter((p) => p.date && Number.isFinite(p.score));
  if (data.length < 2) {
    return <p className="empty">グラフ用の日次が足りません</p>;
  }

  const w = 760;
  const h = 320;
  const padL = 52;
  const padR = 56;
  const padT = 28;
  const padB = 44;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  const scores = data.map((p) => p.score);
  const counts = data
    .map((p) => p.count)
    .filter((c): c is number => c != null && Number.isFinite(c));
  const minScore = 0;
  const maxScore = Math.max(60, SNORE_SCORE_TARGET * 1.2, ...scores, 1);
  const minCount = 0;
  const maxCount = Math.max(200, ...counts, 1);

  const scoreTicks = ticks(minScore, maxScore, 6);
  const countTicks = ticks(minCount, maxCount, 6);

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
  const targetY = yScore(SNORE_SCORE_TARGET);

  return (
    <div className="qe-chart-wrap">
      <svg
        className="qe-chart"
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label="いびきスコアといびき回数の推移"
      >
        {/* grid + left axis (score) */}
        {scoreTicks.map((v) => {
          const y = yScore(v);
          return (
            <g key={`sg-${v}`}>
              <line
                x1={padL}
                x2={w - padR}
                y1={y}
                y2={y}
                stroke={COLOR_GRID}
                strokeWidth={1}
              />
              <text
                x={padL - 8}
                y={y + 3}
                textAnchor="end"
                fontSize={10}
                fill={COLOR_SCORE}
              >
                {Number.isInteger(v) ? v : v.toFixed(1)}
              </text>
            </g>
          );
        })}

        {/* right axis (count) */}
        {countTicks.map((v) => {
          const y = yCount(v);
          return (
            <text
              key={`cg-${v}`}
              x={w - padR + 8}
              y={y + 3}
              textAnchor="start"
              fontSize={10}
              fill={COLOR_COUNT}
            >
              {Math.round(v).toLocaleString("ja-JP")}
            </text>
          );
        })}

        {/* axis titles */}
        <text
          x={14}
          y={padT - 10}
          fontSize={11}
          fontWeight={600}
          fill={COLOR_SCORE}
        >
          いびきスコア
        </text>
        <text
          x={w - 14}
          y={padT - 10}
          textAnchor="end"
          fontSize={11}
          fontWeight={600}
          fill={COLOR_COUNT}
        >
          いびき回数
        </text>

        {/* improvement target */}
        <line
          x1={padL}
          x2={w - padR}
          y1={targetY}
          y2={targetY}
          stroke={COLOR_TARGET}
          strokeWidth={1.8}
          strokeDasharray="6 4"
        />
        <text
          x={padL + 6}
          y={targetY - 6}
          fontSize={10}
          fontWeight={600}
          fill={COLOR_TARGET}
        >
          改善目標 いびきスコア ≤ {SNORE_SCORE_TARGET}
        </text>

        <path
          d={scorePath.join(" ")}
          fill="none"
          stroke={COLOR_SCORE}
          strokeWidth={2.4}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <path
          d={countPath.join(" ")}
          fill="none"
          stroke={COLOR_COUNT}
          strokeWidth={2.2}
          strokeLinejoin="round"
          strokeLinecap="round"
          strokeDasharray="5 3"
        />

        {data.map((p, i) => {
          const treat = isTreatment(p.event);
          return (
            <g key={p.date}>
              <circle
                cx={xAt(i)}
                cy={yScore(p.score)}
                r={treat ? 4.5 : 3}
                fill={treat ? "#e11d48" : COLOR_SCORE}
              />
              {p.count != null ? (
                <circle
                  cx={xAt(i)}
                  cy={yCount(p.count)}
                  r={treat ? 4 : 2.5}
                  fill={treat ? "#059669" : COLOR_COUNT}
                />
              ) : null}
              {i % labelStep === 0 || i === data.length - 1 ? (
                <text
                  x={xAt(i)}
                  y={h - 14}
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
      </svg>
      <div className="qe-chart-legend" aria-hidden>
        <span>
          <i style={{ background: COLOR_SCORE }} />
          いびきスコア（左軸・実線）
        </span>
        <span>
          <i
            style={{
              background: COLOR_COUNT,
              backgroundImage:
                "repeating-linear-gradient(90deg,#4338ca 0 6px,transparent 6px 10px)",
            }}
          />
          いびき回数（右軸・破線）
        </span>
        <span>
          <i
            style={{
              background: COLOR_TARGET,
              backgroundImage:
                "repeating-linear-gradient(90deg,#0f766e 0 6px,transparent 6px 10px)",
            }}
          />
          改善目標（スコア≤{SNORE_SCORE_TARGET}）
        </span>
        <span>
          <i style={{ background: "#e11d48" }} />
          治療日・スコア
        </span>
      </div>
      <p className="meta qe-chart-note">
        改善目標は AutoSnore 公式値ではなく、同種アプリ SnoreLab の「スコア10以下は妨害が少ない目安」を観察用に参照しています。診断ではありません。
      </p>
    </div>
  );
}
