import { KURASHIFT_URL } from "@/lib/nav";
import { loopwareHref } from "@/lib/loopwareLink";
import {
  REGIONS,
  REGION_LABEL,
  goalAt,
  history,
  scorecard,
  sortedEvaluations,
  todayJst,
  total,
  type Region,
} from "@/lib/uiuxScorecard";

/**
 * ホームの「UI/UX 現在地」。3アプリを世界・日本の比較相手で採点した結果と固定ゴール、推移、改善ポイント。
 * データは config/uiux_scorecard.json（採点は末尾に追加、ゴールは年1回だけ見直す）。
 */

function appHref(key: string, fallback: string): string {
  if (key === "kurashift") return KURASHIFT_URL;
  if (key === "loopware") return loopwareHref("/desk", { from: "dashboard" });
  return fallback;
}

function Spark({ points, goal }: { points: number[]; goal: number }) {
  const w = 72;
  const h = 22;
  const y = (v: number) => h - 2 - (Math.max(0, Math.min(100, v)) / 100) * (h - 4);
  const x = (i: number) => (points.length <= 1 ? w - 3 : 3 + (i * (w - 6)) / (points.length - 1));
  return (
    <svg className="uiux-spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <line x1={0} x2={w} y1={y(goal)} y2={y(goal)} className="uiux-spark-goal" />
      {points.length > 1 ? (
        <polyline points={points.map((v, i) => `${x(i)},${y(v)}`).join(" ")} className="uiux-spark-line" />
      ) : null}
      {points.length ? <circle cx={x(points.length - 1)} cy={y(points[points.length - 1])} r={2.5} className="uiux-spark-dot" /> : null}
    </svg>
  );
}

function Delta({ now, prev }: { now: number; prev: number | null }) {
  if (prev == null) return <span className="uiux-delta muted">初回</span>;
  const d = now - prev;
  if (d === 0) return <span className="uiux-delta muted">±0</span>;
  return <span className={`uiux-delta ${d > 0 ? "up" : "down"}`}>{d > 0 ? `+${d}` : d}</span>;
}

export default function HomeUiuxScoreBand() {
  const evals = sortedEvaluations();
  const latest = evals[evals.length - 1];
  if (!latest) return null;
  const today = todayJst();
  const goal = goalAt(today) ?? scorecard.goals[0];
  if (!goal) return null;
  const reviewDue = today >= goal.review_on;
  /** 目標の地域を先に並べる */
  const order: Region[] = [goal.target_region, ...REGIONS.filter((r) => r !== goal.target_region)];
  const axisLabel = Object.fromEntries(scorecard.axes.map((a) => [a.key, a.label]));

  return (
    <article className="card uiux-band" style={{ marginBottom: 16 }}>
      <header>
        <span className="lvl">UI/UX</span>
        <strong>3アプリの現在地</strong>
        <span className="meta uiux-asof">
          {latest.date} 採点 · {latest.method}
        </span>
      </header>
      <p className="sum uiux-goal">
        ゴール <b>{goal.review_on.slice(0, 4)}年に{REGION_LABEL[goal.target_region]}一流水準 {goal[goal.target_region]} 点</b>
        {REGIONS.filter((r) => r !== goal.target_region).map((r) => `（参考：${REGION_LABEL[r]}一流水準 ${goal[r]} 点）`)}
        ・ {goal.set_on} 設定、固定。次の見直し {goal.review_on}
        {reviewDue ? <span className="uiux-review-due">見直しの時期です</span> : null}
      </p>

      <div className="uiux-table" role="table" aria-label="UI/UX点数">
        <div className="uiux-row uiux-head" role="row">
          <span role="columnheader">アプリ</span>
          {order.map((r) => (
            <span key={r} role="columnheader">
              {REGION_LABEL[r]}（{r === goal.target_region ? "目標" : "参考"} {goal[r]}）
            </span>
          ))}
        </div>
        {scorecard.apps.map((app) => (
          <div className="uiux-row" role="row" key={app.key}>
            <span role="cell" className="uiux-app">
              <a href={appHref(app.key, app.href)} target={app.key === "dashboard" ? undefined : "_blank"} rel="noopener noreferrer">
                {app.label}
              </a>
            </span>
            {order.map((r) => {
              const h = history(app.key, r, evals);
              const now = h[h.length - 1]?.score ?? 0;
              const prev = h.length > 1 ? h[h.length - 2].score : null;
              const pct = Math.min(100, Math.round((now / goal[r]) * 100));
              return (
                <span role="cell" key={r} className="uiux-cell">
                  <span className="uiux-score">{now}</span>
                  <Delta now={now} prev={prev} />
                  <span className="uiux-meter" aria-label={`目標まで ${Math.max(0, goal[r] - now)} 点`}>
                    <span style={{ width: `${pct}%` }} className={now >= goal[r] ? "done" : ""} />
                  </span>
                  <Spark points={h.map((p) => p.score)} goal={goal[r]} />
                </span>
              );
            })}
          </div>
        ))}
      </div>

      {scorecard.apps.map((app) => {
        const s = latest.scores[app.key];
        const imps = latest.improvements[app.key] || [];
        if (!s) return null;
        return (
          <details className="uiux-detail" key={app.key}>
            <summary>
              {app.label} の項目別と改善ポイント（{imps.length}件）
            </summary>
            <table className="uiux-axes">
              <thead>
                <tr>
                  <th>項目</th>
                  {order.map((r) => (
                    <th key={r}>{REGION_LABEL[r]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {scorecard.axes.map((a) => (
                  <tr key={a.key} title={a.question}>
                    <td>{a.label}</td>
                    {order.map((r) => (
                      <td key={r}>{s[r]?.[a.key] ?? "—"}</td>
                    ))}
                  </tr>
                ))}
                <tr className="uiux-total">
                  <td>合計（100点）</td>
                  {order.map((r) => (
                    <td key={r}>{total(s[r]) ?? "—"}</td>
                  ))}
                </tr>
              </tbody>
            </table>
            {imps.length ? (
              <ol className="uiux-imps">
                {imps.map((m, i) => (
                  <li key={i}>
                    <span className="uiux-imp-axis">{axisLabel[m.axis] || m.axis}</span>
                    <span className="uiux-imp-gap">比較相手との差：{m.gap}</span>
                    <span className="uiux-imp-next">次の一手：{m.next}</span>
                  </li>
                ))}
              </ol>
            ) : null}
          </details>
        );
      })}

      <details className="uiux-detail">
        <summary>比較相手と項目ごとの基準</summary>
        <p className="uiux-bench">
          {REGIONS.map((r) => (
            <span key={r}>
              <b>{REGION_LABEL[r]}：</b>
              {scorecard.benchmarks[r].map((b, i) => (
                <span key={b.name}>
                  {i ? "、" : ""}
                  <a href={b.url} target="_blank" rel="noopener noreferrer">
                    {b.name} ↗
                  </a>
                </span>
              ))}
              <br />
            </span>
          ))}
        </p>
        <dl className="uiux-bars">
          {scorecard.axes.map((a) => (
            <div key={a.key}>
              <dt>
                {a.label}
                <span className="meta">　{a.question}</span>
              </dt>
              <dd>世界：{a.world_bar}</dd>
              <dd>日本：{a.japan_bar}</dd>
            </div>
          ))}
        </dl>
        <p className="meta uiux-rule">
          各項目は比較相手と同じ水準を10点として採点し、合計を100点に換算。80点（各項目で比較相手の8割）を一流水準とします。採点は3か月ごと（または依頼時）に追加し、過去の点数とゴールは書き換えません。
        </p>
      </details>
    </article>
  );
}
