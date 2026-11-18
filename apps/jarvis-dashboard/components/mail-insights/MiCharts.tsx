import { KINDS, KIND_LABEL, type DayBar, type Kind, type WeekVol } from "@/lib/mailInsights";

/** 振り返り画面のグラフ（サーバーで描く SVG。ブラウザの JS は使わない） */

export const KIND_COLOR: Record<Kind, string> = {
  sent: "var(--mi-sent)",
  todo: "var(--mi-todo)",
  hesitate: "var(--mi-hes)",
  unseen: "var(--mi-unseen)",
  skip: "var(--mi-skip)",
};

export function KindLegend() {
  return (
    <div className="mi-legend">
      {KINDS.map((k) => (
        <span key={k}>
          <i style={{ background: KIND_COLOR[k] }} />
          {KIND_LABEL[k]}
        </span>
      ))}
    </div>
  );
}

/** 日別の積み上げ棒。上限を超えた日は棒を切って合計を上に書く */
export function DailyChart({ days }: { days: DayBar[] }) {
  const totals = days.map((d) => KINDS.reduce((a, k) => a + d[k], 0));
  const sorted = [...totals].sort((a, b) => a - b);
  // 一括見送りの日に引っぱられないよう、2番目に多い日を基準に上限を決める
  const ref = sorted.length > 1 ? sorted[sorted.length - 2] : sorted[0] || 0;
  const step = ref > 40 ? 20 : ref > 16 ? 10 : 5;
  const max = Math.max(step, Math.ceil((ref * 1.15) / step) * step);
  const L = 30;
  const T = 14;
  const H = 150;
  const W = 500;
  const bw = W / Math.max(1, days.length);
  const ticks = [];
  for (let v = 0; v <= max; v += step) ticks.push(v);
  return (
    <svg viewBox={`0 0 ${L + W + 6} ${T + H + 22}`} width="100%" role="img" aria-label="日別の判断の内訳">
      {ticks.map((v) => {
        const y = T + H - (v / max) * H;
        return (
          <g key={v}>
            <line x1={L} x2={L + W} y1={y} y2={y} stroke="var(--line)" strokeWidth={1} />
            <text x={L - 6} y={y + 3} textAnchor="end" className="mi-axis">
              {v}
            </text>
          </g>
        );
      })}
      {days.map((d, i) => {
        const x = L + i * bw + bw * 0.2;
        const w = bw * 0.6;
        let used = 0;
        const rects = [];
        for (const k of KINDS) {
          const v = Math.min(d[k], max - used);
          if (v <= 0) continue;
          const h = (v / max) * H;
          const y = T + H - ((used + v) / max) * H;
          used += v;
          rects.push(<rect key={k} x={x} y={y} width={w} height={h} rx={2} fill={KIND_COLOR[k]} />);
        }
        const over = totals[i] > max;
        const showLabel = days.length <= 16 || i % 2 === days.length % 2 || i === days.length - 1;
        return (
          <g key={d.key}>
            <title>{`${d.label}: ${KINDS.filter((k) => d[k]).map((k) => `${KIND_LABEL[k]}${d[k]}`).join("・") || "なし"}`}</title>
            {rects}
            {over ? (
              <>
                <path d={`M${x - 2} ${T + 8} l${w + 4} -5 M${x - 2} ${T + 13} l${w + 4} -5`} stroke="var(--card)" strokeWidth={3} />
                <text x={x + w / 2} y={T - 3} textAnchor="middle" className="mi-axis mi-strong">
                  {totals[i]}
                </text>
              </>
            ) : null}
            {showLabel ? (
              <text x={x + w / 2} y={T + H + 15} textAnchor="middle" className="mi-axis">
                {d.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

/** 時間帯（0〜23時）。上位の山だけ色を付ける */
export function HourChart({ hours, peaks }: { hours: number[]; peaks: number[] }) {
  const max = Math.max(1, ...hours);
  const L = 6;
  const T = 18;
  const H = 96;
  const W = 348;
  const bw = W / 24;
  return (
    <svg viewBox={`0 0 ${L + W + 6} ${T + H + 22}`} width="100%" role="img" aria-label="時間帯別の判断件数">
      {hours.map((v, i) => {
        const h = Math.max(1.5, (v / max) * H);
        const peak = peaks.includes(i);
        return (
          <g key={i}>
            <title>{`${i}時台: ${v}件`}</title>
            <rect x={L + i * bw + 1.5} y={T + H - h} width={bw - 3} height={h} rx={2} fill={peak ? "var(--accent)" : "var(--mi-skip)"} />
            {peak && v ? (
              <text x={L + i * bw + bw / 2} y={T + H - h - 4} textAnchor="middle" className="mi-axis mi-strong">
                {v}
              </text>
            ) : null}
            {i % 3 === 0 ? (
              <text x={L + i * bw + bw / 2} y={T + H + 15} textAnchor="middle" className="mi-axis">
                {i}時
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

/** 週ごとの受信量（その他＝面、パートナー＝線＋面）。パートナーの最大週に点 */
export function WeeklyChart({ weeks }: { weeks: WeekVol[] }) {
  if (weeks.length < 2) return null;
  const top = Math.max(10, ...weeks.map((w) => Math.max(w.general, w.partner)));
  const step = top > 150 ? 100 : top > 60 ? 50 : 20;
  const max = Math.ceil(top / step) * step;
  const L = 36;
  const T = 16;
  const H = 120;
  const W = 940;
  const dx = W / (weeks.length - 1);
  const pt = (i: number, v: number) => [L + i * dx, T + H - (v / max) * H] as const;
  const path = (key: "partner" | "general") => weeks.map((w, i) => pt(i, w[key]).map((n) => n.toFixed(1)).join(" ")).join(" L");
  const area = (key: "partner" | "general") => `M${path(key)} L${L + W} ${T + H} L${L} ${T + H} Z`;
  let best = 0;
  weeks.forEach((w, i) => {
    if (w.partner > weeks[best].partner) best = i;
  });
  const [bx, by] = pt(best, weeks[best].partner);
  const ticks = [];
  for (let v = 0; v <= max; v += step) ticks.push(v);
  const every = weeks.length > 12 ? 2 : 1;
  return (
    <svg viewBox={`0 0 ${L + W + 24} ${T + H + 22}`} width="100%" role="img" aria-label="週ごとに届いたメールの件数">
      {ticks.map((v) => {
        const y = T + H - (v / max) * H;
        return (
          <g key={v}>
            <line x1={L} x2={L + W} y1={y} y2={y} stroke="var(--line)" />
            <text x={L - 6} y={y + 3} textAnchor="end" className="mi-axis">
              {v}
            </text>
          </g>
        );
      })}
      <path d={area("general")} fill="var(--mi-skip)" fillOpacity={0.18} />
      <path d={`M${path("general")}`} fill="none" stroke="var(--mi-skip)" strokeWidth={2.2} strokeLinejoin="round" />
      <path d={area("partner")} fill="var(--accent)" fillOpacity={0.14} />
      <path d={`M${path("partner")}`} fill="none" stroke="var(--accent)" strokeWidth={2.4} strokeLinejoin="round" />
      {weeks.map((w, i) => (
        <g key={w.key}>
          <title>{`${w.label}の週: パートナー${w.partner}・その他${w.general}`}</title>
          <circle cx={pt(i, w.partner)[0]} cy={pt(i, w.partner)[1]} r={9} fill="transparent" />
          {i % every === 0 ? (
            <text x={L + i * dx} y={T + H + 15} textAnchor="middle" className="mi-axis">
              {w.label}
            </text>
          ) : null}
        </g>
      ))}
      {weeks[best].partner > 0 ? (
        <>
          <circle cx={bx} cy={by} r={4.5} fill="var(--accent)" />
          <text x={bx} y={by - 9} textAnchor="middle" className="mi-axis mi-accent">
            {weeks[best].partner}件
          </text>
        </>
      ) : null}
    </svg>
  );
}
