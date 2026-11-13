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
  type Snapshot,
} from "@/lib/agentMaturity";
import MaturityTaskButton from "./MaturityTaskButton";

/** /agent-team の「成熟度」タブ（サーバー描画）。物差しは config、実測は週次の記録 */

function todayJst(): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" }).format(new Date());
}

function Lv({ v }: { v: number | null }) {
  if (v == null) return <span className="mat-lv is-none">未計測</span>;
  return <span className={`mat-lv lv-${Math.floor(v)}`}>L{v}</span>;
}

/** 先週（1つ前の計測）からの差。前回が無い・どちらか未計測なら理由を出す */
function WeekDelta({ now, prev, hasPrev }: { now: number | null; prev: number | null; hasPrev: boolean }) {
  if (!hasPrev) return <span className="meta">初回</span>;
  if (now == null || prev == null) return <span className="meta">—</span>;
  const d = Math.round((now - prev) * 10) / 10;
  return <span className={`mat-delta ${d > 0 ? "up" : d < 0 ? "down" : ""}`}>{d === 0 ? "±0" : `${d > 0 ? "+" : ""}${d}`}</span>;
}

function Trend({ team, axisKey, goal }: { team: Snapshot[]; axisKey: "process" | "output"; goal: number }) {
  const axis = maturityConfig.axes.find((a) => a.key === axisKey)!;
  const pts = team.map((s) => ({ d: s.measured_on, v: axisLevel(axis, s).level })).filter((p) => p.v != null) as { d: string; v: number }[];
  if (!pts.length) return null;
  const w = 220;
  const h = 48;
  const y = (v: number) => h - 6 - ((v - 1) / 4) * (h - 12);
  const x = (i: number) => (pts.length === 1 ? w - 8 : 8 + (i * (w - 16)) / (pts.length - 1));
  return (
    <svg className="mat-trend" width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`${axis.label}の推移`}>
      <line x1={0} x2={w} y1={y(goal)} y2={y(goal)} className="mat-trend-goal" />
      {pts.length > 1 ? <polyline points={pts.map((p, i) => `${x(i)},${y(p.v)}`).join(" ")} className="mat-trend-line" /> : null}
      {pts.map((p, i) => (
        <circle key={p.d} cx={x(i)} cy={y(p.v)} r={2.5} className="mat-trend-dot">
          <title>{`${p.d} L${p.v}`}</title>
        </circle>
      ))}
    </svg>
  );
}

export default async function MaturityPanel() {
  const { team, employees, error } = await loadSnapshots();
  const latest = team[team.length - 1] ?? null;
  const prev = team.length > 1 ? team[team.length - 2] : null;
  const goal = goalAt(todayJst());

  return (
    <section className="mat-panel">
      <p className="at-lead">
        AIエージェント運用の成熟度を、Process（運用のやり方）とOutput（できたもの）に分けて L1〜L5 で見ます。
        実測は毎週土曜に自動で記録し、取れない指標は「未計測」として平均に入れません。
        {goal ? ` ゴールは ${goal.review_on.slice(0, 4)} 年に Process L${goal.process}・Output L${goal.output}（${goal.set_on} 設定、${goal.review_on} に見直し）。` : ""}
      </p>
      {error ? <p className="meta">記録を読めませんでした（{error}）。週次の表がまだ無い可能性があります。</p> : null}
      {!latest ? (
        <p className="meta">まだ計測の記録がありません。最初の計測は次の土曜（または手動実行）に入ります。</p>
      ) : (
        <>
          <div className="mat-axes">
            {maturityConfig.axes.map((axis) => {
              const a = axisLevel(axis, latest);
              const p = prev ? axisLevel(axis, prev).level : null;
              const g = goal ? goal[axis.key] : 4;
              return (
                <div className="mat-axis-card" key={axis.key}>
                  <div className="mat-axis-head">
                    <strong>{axis.label}</strong>
                    <Lv v={a.level} />
                    <span className="meta">先週比</span>
                    <WeekDelta now={a.level} prev={p} hasPrev={Boolean(prev)} />
                    <span className="meta">
                      {a.measured}/{a.total} 項目を計測 · 目標 L{g}
                    </span>
                  </div>
                  <Trend team={team} axisKey={axis.key} goal={g} />
                </div>
              );
            })}
          </div>

          <h3 className="mat-h">優先改善（低い項目から3つ）</h3>
          <ol className="mat-prio">
            {priorities(latest, prev).map((p) => (
              <li key={p.item.key}>
                <span className="mat-prio-item">
                  {p.item.label} <Lv v={p.level} />
                </span>
                <span className="meta">{p.why}</span>
                <span className="mat-prio-act">
                  次の一手：{p.action} <MaturityTaskButton itemKey={p.item.key} actionIndex={0} why={p.why} />
                </span>
              </li>
            ))}
          </ol>

          {maturityConfig.axes.map((axis) => (
            <div key={axis.key} className="at-table-wrap">
              <h3 className="mat-h">{axis.label}</h3>
              <table className="at-table mat-table">
                <thead>
                  <tr>
                    <th>項目</th>
                    <th>レベル</th>
                    <th>先週比</th>
                    <th>指標と実測（{latest.measured_on}）</th>
                    <th>世界水準の状態</th>
                  </tr>
                </thead>
                <tbody>
                  {axis.items.map((item) => (
                    <tr key={item.key}>
                      <td>{item.label}</td>
                      <td>
                        <Lv v={itemLevel(item, latest)} />
                      </td>
                      <td>
                        <WeekDelta now={itemLevel(item, latest)} prev={itemLevel(item, prev)} hasPrev={Boolean(prev)} />
                      </td>
                      <td>
                        <ul className="mat-metrics">
                          {item.metrics.map((k) => {
                            const def = maturityConfig.metrics[k];
                            const v = metricValue(latest, k);
                            const pv = metricValue(prev, k);
                            return (
                              <li key={k} title={`出どころ: ${def.source}`}>
                                {def.label}：
                                {v ? (
                                  <>
                                    <b>{formatMetric(def, v)}</b> <Lv v={metricLevel(def, v.value)} />
                                    {pv ? <span className="meta"> 先週 {formatMetric(def, { value: pv.value })}</span> : null}
                                    {v.note ? <span className="meta"> {v.note}</span> : null}
                                  </>
                                ) : (
                                  <span className="meta">未計測（{missingReason(latest, k)}）</span>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      </td>
                      <td className="meta">{item.world}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          {employees.length ? (
            <div className="at-table-wrap">
              <h3 className="mat-h">社員別（判断ログに社員番号がある社員・28日）</h3>
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
            </div>
          ) : null}

          <details className="mat-rule">
            <summary>レベルの意味と付け方</summary>
            <ul>
              {Object.entries(maturityConfig.level_labels).map(([k, v]) => (
                <li key={k}>
                  L{k}：{v}
                </li>
              ))}
            </ul>
            <p className="meta">
              指標ごとに固定の線（config/agent_maturity.json）でレベルを付け、項目は計測できた指標の平均、軸は計測できた項目の平均です。線とゴールは年1回だけ見直します。
            </p>
          </details>
        </>
      )}
    </section>
  );
}
