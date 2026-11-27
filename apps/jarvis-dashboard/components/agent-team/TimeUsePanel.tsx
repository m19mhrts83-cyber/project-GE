import data from "@/data/timeUse.json";
import { buildRows, weekStartOf, type TimeUseRow, type TimeUseWeek } from "@/lib/timeUse";

/**
 * 松野さんの時間の使い方（週ごと）。判断の比率が上がり、直しが減れば良い。方針づくりは別枠で数だけ並べる。
 * 記録は data/timeUse.json（1週1行）。サーバー描画・SVG だけ（スマホ幅で viewBox が縮む）。
 */

const pct = (r: number | null) => (r == null ? "—" : `${Math.round(r * 100)}%`);
const md = (s: string) => s.slice(5).replace("-", "/");

function diff(cur: number, prev: number | undefined) {
  if (prev == null) return null;
  const d = cur - prev;
  return d === 0 ? "±0" : d > 0 ? `+${d}` : `${d}`;
}

function Chart({ rows }: { rows: TimeUseRow[] }) {
  const W = 320;
  const H = 150;
  const L = 8;
  const R = 8;
  const T = 10;
  const B = 24;
  const plotW = W - L - R;
  const plotH = H - T - B;
  const max = Math.max(5, ...rows.flatMap((r) => [r.decisions, r.fixes]));
  const slot = plotW / rows.length;
  const bw = Math.min(14, slot / 2.6);
  const y = (v: number) => T + plotH - (v / max) * plotH;
  const yr = (v: number) => T + plotH - v * plotH;
  const pts = rows.map((r, i) => (r.ratio == null ? null : [L + slot * i + slot / 2, yr(r.ratio)] as const));
  const line = pts.filter((p): p is readonly [number, number] => p != null).map((p) => p.join(",")).join(" ");
  return (
    <svg className="tu-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="週ごとの判断・直しの件数と判断の比率">
      <line x1={L} x2={W - R} y1={T + plotH} y2={T + plotH} stroke="var(--line)" />
      {rows.map((r, i) => {
        const cx = L + slot * i + slot / 2;
        return (
          <g key={r.week_start}>
            <rect x={cx - bw - 1} y={y(r.decisions)} width={bw} height={T + plotH - y(r.decisions)} fill="var(--accent)" rx={2} />
            <rect x={cx + 1} y={y(r.fixes)} width={bw} height={T + plotH - y(r.fixes)} fill="var(--med)" rx={2} />
            <text x={cx} y={H - 8} fontSize={9} textAnchor="middle" fill="var(--muted)">
              {md(r.week_start)}
            </text>
          </g>
        );
      })}
      {line && rows.length > 1 ? <polyline points={line} fill="none" stroke="var(--info)" strokeWidth={2} /> : null}
      {pts.map((p, i) => (p ? <circle key={i} cx={p[0]} cy={p[1]} r={3} fill="var(--info)" /> : null))}
    </svg>
  );
}

export default function TimeUsePanel() {
  const rows = buildRows((data as { weeks: TimeUseWeek[] }).weeks);
  if (!rows.length) return null;
  const thisWeek = weekStartOf(new Date());
  const idx = rows.findIndex((r) => r.week_start === thisWeek);
  const curIdx = idx >= 0 ? idx : rows.length - 1;
  const cur = rows[curIdx];
  const prev = rows[curIdx - 1];
  const isThis = cur.week_start === thisWeek;
  const recent = rows.slice(-12);
  const dRatio = prev && cur.ratio != null && prev.ratio != null ? Math.round((cur.ratio - prev.ratio) * 100) : null;

  return (
    <section className="card tu" id="time-use">
      <style>{`
        .tu-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:8px 0}
        .tu-cell{border:1px solid var(--line);border-radius:8px;padding:8px;min-width:0}
        .tu-cell b{display:block;font-size:20px;line-height:1.2}
        .tu-cell small{color:var(--muted);font-size:11px}
        .tu-cell .d{font-size:11px;color:var(--muted)}
        .tu-chart{width:100%;height:auto;max-width:520px;display:block}
        .tu-legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:11px;color:var(--muted);margin:4px 0}
        .tu-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
        @media (max-width:480px){.tu-grid{grid-template-columns:repeat(2,1fr)}}
      `}</style>
      <header>
        <strong>時間の使い方</strong>
        <span className="meta">判断の比率が上がり、直しが減れば良い</span>
      </header>
      <p className="meta">
        {isThis ? "今週" : `最新（${md(cur.week_start)} の週。今週分は未記録）`}
        ・{md(cur.week_start)} 〜{cur.memo ? `　${cur.memo}` : ""}
      </p>
      <div className="tu-grid">
        <div className="tu-cell">
          <small>判断の比率</small>
          <b>{pct(cur.ratio)}</b>
          <span className="d">{dRatio == null ? "先週なし" : `先週比 ${dRatio > 0 ? "+" : ""}${dRatio}pt`}</span>
        </div>
        <div className="tu-cell">
          <small>判断</small>
          <b>{cur.decisions}</b>
          <span className="d">先週比 {diff(cur.decisions, prev?.decisions) ?? "—"}</span>
        </div>
        <div className="tu-cell">
          <small>直し</small>
          <b>{cur.fixes}</b>
          <span className="d">先週比 {diff(cur.fixes, prev?.fixes) ?? "—"}</span>
        </div>
        <div className="tu-cell">
          <small>方針づくり（別枠）</small>
          <b>{cur.policy}</b>
          <span className="d">先週比 {diff(cur.policy, prev?.policy) ?? "—"}</span>
        </div>
      </div>
      <Chart rows={recent} />
      <div className="tu-legend">
        <span><i style={{ background: "var(--accent)" }} />判断</span>
        <span><i style={{ background: "var(--med)" }} />直し</span>
        <span><i style={{ background: "var(--info)" }} />判断の比率（線）</span>
      </div>
    </section>
  );
}
