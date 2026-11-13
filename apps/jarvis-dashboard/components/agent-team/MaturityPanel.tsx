import type { CSSProperties } from "react";
import {
  axisLevel,
  formatMetric,
  goalAt,
  itemLevel,
  loadSnapshots,
  maturityConfig,
  metricLevel,
  metricValue,
  missingReason,
  priorities,
  type AxisDef,
  type Snapshot,
} from "@/lib/agentMaturity";
import MaturityCountUp from "./MaturityCountUp";
import MaturityTaskButton from "./MaturityTaskButton";

/**
 * /agent-team の「成熟度」タブ（サーバー描画）。物差しは config、実測は週次の記録。
 * 見る順: ① 2軸のリング（今どこ・目標まであと何） → ② 10項目のバー（どこが弱い） → ③ 次の一手（何をする）。
 * 動きは CSS（リング・バー・登場）と数え上げだけ。動きを減らす設定では止める。
 */

type Vars = CSSProperties & Record<`--${string}`, string | number>;

function todayJst(): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" }).format(new Date());
}

function tone(v: number | null): string {
  if (v == null) return "none";
  return `l${Math.min(5, Math.max(1, Math.floor(v)))}`;
}

function Lv({ v }: { v: number | null }) {
  if (v == null) return <span className="mat-lv is-none">未計測</span>;
  return <span className={`mat-lv lv-${Math.floor(v)}`}>L{v}</span>;
}

function deltaOf(now: number | null, prev: number | null): number | null {
  if (now == null || prev == null) return null;
  return Math.round((now - prev) * 10) / 10;
}

function DeltaChip({ d, hasPrev }: { d: number | null; hasPrev: boolean }) {
  if (!hasPrev) return <span className="mx-chip is-first">初回の計測</span>;
  if (d == null) return <span className="mx-chip">先週比 —</span>;
  const cls = d > 0 ? "up" : d < 0 ? "down" : "";
  return (
    <span className={`mx-chip ${cls}`}>
      先週比 {d > 0 ? "▲ +" : d < 0 ? "▼ " : "± "}
      {d === 0 ? "0" : d}
    </span>
  );
}

/** L1〜L5 のリング。今のレベルまで伸び、目標の位置に印 */
function Ring({ level, goal, idx, label, sub }: { level: number | null; goal: number; idx: number; label: string; sub: string }) {
  const r = 70;
  const c = 2 * Math.PI * r;
  const frac = level == null ? 0 : level / 5;
  const goalAngle = (goal / 5) * 360 - 90;
  const gx = 90 + r * Math.cos((goalAngle * Math.PI) / 180);
  const gy = 90 + r * Math.sin((goalAngle * Math.PI) / 180);
  return (
    <div className="mx-ring" style={{ "--d": `${idx * 180}ms` } as Vars}>
      <svg viewBox="0 0 180 180" role="img" aria-label={`${label} ${level == null ? "未計測" : `L${level}`}、目標 L${goal}`}>
        <defs>
          <linearGradient id={`mx-grad-${idx}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#5eead4" />
            <stop offset="100%" stopColor="#38bdf8" />
          </linearGradient>
        </defs>
        <circle cx={90} cy={90} r={r} className="mx-ring-track" />
        {[1, 2, 3, 4].map((k) => {
          const a = ((k / 5) * 360 - 90) * (Math.PI / 180);
          return <line key={k} x1={90 + (r - 9) * Math.cos(a)} y1={90 + (r - 9) * Math.sin(a)} x2={90 + (r + 9) * Math.cos(a)} y2={90 + (r + 9) * Math.sin(a)} className="mx-ring-tick" />;
        })}
        <circle
          cx={90}
          cy={90}
          r={r}
          className="mx-ring-fill"
          stroke={`url(#mx-grad-${idx})`}
          transform="rotate(-90 90 90)"
          style={{ "--c": c, "--off": c * (1 - frac), strokeDasharray: c } as Vars}
        />
        <circle cx={gx} cy={gy} r={6} className="mx-ring-goal" />
      </svg>
      <div className="mx-ring-center">
        <span className="mx-ring-axis">{label}</span>
        <span className="mx-ring-num">
          {level == null ? "—" : (
            <>
              <small>L</small>
              <MaturityCountUp value={level} delay={idx * 180} />
            </>
          )}
        </span>
        <span className="mx-ring-sub">{sub}</span>
      </div>
    </div>
  );
}

function Spark({ team, axis, goal }: { team: Snapshot[]; axis: AxisDef; goal: number }) {
  const pts = team.map((s) => ({ d: s.measured_on, v: axisLevel(axis, s).level })).filter((p) => p.v != null) as { d: string; v: number }[];
  if (pts.length < 2) return <p className="mx-spark-empty">来週の計測から推移の線が出ます</p>;
  const w = 240;
  const h = 56;
  const y = (v: number) => h - 6 - ((v - 1) / 4) * (h - 12);
  const x = (i: number) => 6 + (i * (w - 12)) / (pts.length - 1);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.v)}`).join(" ");
  return (
    <svg className="mx-spark" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`${axis.label}の推移`}>
      <line x1={0} x2={w} y1={y(goal)} y2={y(goal)} className="mx-spark-goal" />
      <path d={`${d} L${x(pts.length - 1)},${h} L${x(0)},${h} Z`} className="mx-spark-area" />
      <path d={d} className="mx-spark-line" pathLength={1} />
      <circle cx={x(pts.length - 1)} cy={y(pts[pts.length - 1].v)} r={3.5} className="mx-spark-dot" />
    </svg>
  );
}

export default async function MaturityPanel() {
  const { team, employees, error } = await loadSnapshots();
  const latest = team[team.length - 1] ?? null;
  const prev = team.length > 1 ? team[team.length - 2] : null;
  const goal = goalAt(todayJst());

  if (!latest) {
    return (
      <section className="mat-panel">
        {error ? <p className="meta">記録を読めませんでした（{error}）。</p> : null}
        <p className="meta">まだ計測の記録がありません。最初の計測は次の土曜（または手動実行）に入ります。</p>
      </section>
    );
  }

  const axes = maturityConfig.axes.map((axis) => {
    const a = axisLevel(axis, latest);
    const p = prev ? axisLevel(axis, prev).level : null;
    const g = goal ? goal[axis.key] : 4;
    return { axis, ...a, prev: p, goal: g };
  });
  const measuredAll = axes.reduce((s, a) => s + a.measured, 0);
  const totalAll = axes.reduce((s, a) => s + a.total, 0);
  const prio = priorities(latest, prev);
  let rowIdx = 0;

  return (
    <section className="mat-panel mx">
      {/* ① いまの位置 */}
      <div className="mx-hero">
        <div className="mx-hero-head">
          <div>
            <p className="mx-eyebrow">AIエージェント運用の成熟度</p>
            <h2 className="mx-title">
              {goal ? `${goal.review_on.slice(0, 4)}年に L${goal.process} へ` : "L4 へ"}
            </h2>
          </div>
          <p className="mx-hero-meta">
            {latest.measured_on} 計測 · {measuredAll}/{totalAll} 項目
            <br />
            毎週土曜 8:00 に自動で更新
          </p>
        </div>
        <div className="mx-rings">
          {axes.map((a, i) => {
            const gap = a.level == null ? null : Math.round((a.goal - a.level) * 10) / 10;
            return (
              <div key={a.axis.key} className="mx-ring-wrap">
                <Ring
                  level={a.level}
                  goal={a.goal}
                  idx={i}
                  label={a.axis.key === "process" ? "Process" : "Output"}
                  sub={a.axis.key === "process" ? "運用のやり方" : "できたもの"}
                />
                <div className="mx-ring-foot">
                  <DeltaChip d={deltaOf(a.level, a.prev)} hasPrev={Boolean(prev)} />
                  <span className="mx-goal-gap">
                    {gap == null ? "未計測" : gap <= 0 ? "目標に到達" : (
                      <>
                        目標 L{a.goal} まで <b>あと {gap}</b>
                      </>
                    )}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
        <ol className="mx-ladder" aria-label="レベルの意味">
          {Object.entries(maturityConfig.level_labels).map(([k, v]) => (
            <li key={k} className={axes.some((a) => a.level != null && Math.floor(a.level) === Number(k)) ? "is-here" : ""}>
              <b>L{k}</b>
              <span>{v}</span>
            </li>
          ))}
        </ol>
      </div>

      {/* ② 次の一手 */}
      <h3 className="mx-h">
        次の一手 <span>低い項目から順に</span>
      </h3>
      <div className="mx-next">
        {prio.map((p, i) => (
          <article key={p.item.key} className={`mx-next-card t-${tone(p.level)}`} style={{ "--d": `${500 + i * 120}ms` } as Vars}>
            <span className="mx-next-rank">{i + 1}</span>
            <div className="mx-next-body">
              <p className="mx-next-item">
                {p.item.label} <Lv v={p.level} />
              </p>
              <p className="mx-next-act">{p.action}</p>
              {p.level == null || (p.prev != null && p.level < p.prev) ? <p className="mx-next-why">{p.why}</p> : null}
              <MaturityTaskButton itemKey={p.item.key} actionIndex={0} why={p.why} />
            </div>
          </article>
        ))}
      </div>

      {/* ③ 10項目のバー */}
      <div className="mx-axes">
        {axes.map((a) => (
          <section key={a.axis.key} className="mx-axis">
            <header className="mx-axis-head">
              <h3>{a.axis.label}</h3>
              <Lv v={a.level} />
            </header>
            <Spark team={team} axis={a.axis} goal={a.goal} />
            {a.axis.items.map((item) => {
              const lv = itemLevel(item, latest);
              const pv = itemLevel(item, prev);
              const d = deltaOf(lv, pv);
              const i = rowIdx++;
              return (
                <details key={item.key} className={`mx-row t-${tone(lv)}`} style={{ "--d": `${300 + i * 70}ms`, "--w": lv == null ? 0 : lv / 5, "--g": a.goal / 5 } as Vars}>
                  <summary>
                    <span className="mx-row-label">{item.label}</span>
                    <span className="mx-bar">
                      {lv == null ? <span className="mx-bar-none">未計測</span> : <span className="mx-bar-fill" />}
                      <span className="mx-bar-goal" title={`目標 L${a.goal}`} />
                    </span>
                    <span className="mx-row-lv">
                      {lv == null ? "—" : `L${lv}`}
                      {d != null && d !== 0 ? <i className={d > 0 ? "up" : "down"}>{d > 0 ? `+${d}` : d}</i> : null}
                    </span>
                  </summary>
                  <div className="mx-row-detail">
                    <ul>
                      {item.metrics.map((k) => {
                        const def = maturityConfig.metrics[k];
                        const v = metricValue(latest, k);
                        const pmv = metricValue(prev, k);
                        return (
                          <li key={k} title={`出どころ: ${def.source}`}>
                            <span>{def.label}</span>
                            {v ? (
                              <span>
                                <b>{formatMetric(def, v)}</b> <Lv v={metricLevel(def, v.value)} />
                                {pmv ? <span className="meta"> 先週 {formatMetric(def, { value: pmv.value })}</span> : null}
                                {v.note ? <span className="meta"> {v.note}</span> : null}
                              </span>
                            ) : (
                              <span className="meta">未計測：{missingReason(latest, k)}</span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                    <p className="mx-world">
                      <b>世界水準</b> {item.world}
                    </p>
                  </div>
                </details>
              );
            })}
          </section>
        ))}
      </div>
      <p className="mx-hint">項目を押すと、指標の実測値と世界水準の状態が開きます。縦の点線が目標（L{goal?.process ?? 4}）です。</p>

      {employees.length ? (
        <details className="mat-rule">
          <summary>社員別（判断ログに社員番号がある社員・28日）</summary>
          <table className="at-table mat-table">
            <thead>
              <tr>
                <th>社員</th>
                <th>判断の件数</th>
                <th>採用率（採った÷採った＋見送った）</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((e) => {
                const d = metricValue(e, "decisions_28d");
                const t = metricValue(e, "take_rate");
                return (
                  <tr key={e.scope}>
                    <td>{e.scope}</td>
                    <td>{d ? `${d.value}件` : "—"}</td>
                    <td>{t ? `${Math.round(t.value * 100)}%（${t.num}/${t.den}）` : "未計測（5件未満）"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </details>
      ) : null}

      <details className="mat-rule">
        <summary>レベルの付け方</summary>
        <p className="meta">
          指標ごとに固定の線（config/agent_maturity.json）でレベルを付け、項目は計測できた指標の平均、軸は計測できた項目の平均です。取れない指標は「未計測」として平均に入れません。線とゴールは年1回だけ見直します
          {goal ? `（${goal.set_on} 設定、${goal.review_on} に見直し）` : ""}。
        </p>
      </details>
    </section>
  );
}
