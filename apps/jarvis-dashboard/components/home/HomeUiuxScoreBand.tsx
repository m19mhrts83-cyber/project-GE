import type { CSSProperties } from "react";
import { KURASHIFT_URL } from "@/lib/nav";
import { loopwareHref } from "@/lib/loopwareLink";
import MaturityCountUp from "@/components/agent-team/MaturityCountUp";
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
 * 見る順: アプリごとの点数とゴールまでの距離 → いちばん効く次の一手 → 項目別（開くと出る）。
 */

type Vars = CSSProperties & Record<`--${string}`, string | number>;

function appHref(key: string, fallback: string): string {
  if (key === "kurashift") return KURASHIFT_URL;
  if (key === "loopware") return loopwareHref("/desk", { from: "dashboard" });
  return fallback;
}

function Delta({ now, prev }: { now: number; prev: number | null }) {
  if (prev == null) return <span className="ux-chip is-first">初回</span>;
  const d = now - prev;
  if (d === 0) return <span className="ux-chip">前回比 ±0</span>;
  return <span className={`ux-chip ${d > 0 ? "up" : "down"}`}>前回比 {d > 0 ? `▲ +${d}` : `▼ ${d}`}</span>;
}

export default function HomeUiuxScoreBand() {
  const evals = sortedEvaluations();
  const latest = evals[evals.length - 1];
  if (!latest) return null;
  const today = todayJst();
  const goal = goalAt(today) ?? scorecard.goals[0];
  if (!goal) return null;
  const reviewDue = today >= goal.review_on;
  const target: Region = goal.target_region;
  const ref: Region = REGIONS.find((r) => r !== target) ?? "world";
  const axisLabel = Object.fromEntries(scorecard.axes.map((a) => [a.key, a.label]));

  return (
    <article className="card ux-band">
      <header className="ux-head">
        <div>
          <p className="ux-eyebrow">UI/UX · 3アプリの現在地</p>
          <h2 className="ux-title">
            {goal.review_on.slice(0, 4)}年に{REGION_LABEL[target]}一流 <b>{goal[target]}点</b>
          </h2>
        </div>
        <p className="ux-asof">
          {latest.date} 採点 · {latest.method}
          <br />
          参考：{REGION_LABEL[ref]}一流 {goal[ref]}点 · 見直し {goal.review_on}
          {reviewDue ? <span className="uiux-review-due">見直しの時期です</span> : null}
        </p>
      </header>

      <div className="ux-apps">
        {scorecard.apps.map((app, i) => {
          const h = history(app.key, target, evals);
          const now = h[h.length - 1]?.score ?? 0;
          const prev = h.length > 1 ? h[h.length - 2].score : null;
          const refNow = history(app.key, ref, evals).at(-1)?.score ?? null;
          const gap = Math.max(0, goal[target] - now);
          const top = (latest.improvements[app.key] || [])[0];
          return (
            <section key={app.key} className="ux-app" style={{ "--d": `${i * 120}ms`, "--s": now / 100, "--r": (refNow ?? 0) / 100, "--g": goal[target] / 100 } as Vars}>
              <a className="ux-app-name" href={appHref(app.key, app.href)} target={app.key === "dashboard" ? undefined : "_blank"} rel="noopener noreferrer">
                {app.label} <span aria-hidden>↗</span>
              </a>
              <div className="ux-score-row">
                <span className="ux-score">
                  <MaturityCountUp value={now} decimals={0} delay={i * 120} />
                  <small>点</small>
                </span>
                <Delta now={now} prev={prev} />
              </div>
              <div className="ux-track" role="img" aria-label={`${REGION_LABEL[target]} ${now}点、目標 ${goal[target]}点、${REGION_LABEL[ref]} ${refNow ?? "—"}点`}>
                <span className="ux-track-fill" />
                {refNow != null ? <span className="ux-track-ref" title={`${REGION_LABEL[ref]} ${refNow}点`} /> : null}
                <span className="ux-track-goal" />
              </div>
              <p className="ux-gap">
                {gap === 0 ? (
                  <b>目標に到達</b>
                ) : (
                  <>
                    目標まで <b>あと {gap}点</b>
                  </>
                )}
                {refNow != null ? <span> · {REGION_LABEL[ref]} {refNow}点</span> : null}
              </p>
              {top ? (
                <p className="ux-next">
                  <span>次の一手 · {axisLabel[top.axis] || top.axis}</span>
                  {top.next}
                </p>
              ) : null}
            </section>
          );
        })}
      </div>
      <p className="ux-legend">
        <i className="k-fill" />
        {REGION_LABEL[target]}の点数　<i className="k-ref" />
        {REGION_LABEL[ref]}（参考）　<i className="k-goal" />
        目標 {goal[target]}点
      </p>

      {scorecard.apps.map((app) => {
        const s = latest.scores[app.key];
        const imps = latest.improvements[app.key] || [];
        if (!s) return null;
        return (
          <details className="ux-detail" key={app.key}>
            <summary>
              <span>{app.label}</span>
              <span className="meta">項目別と改善ポイント {imps.length}件</span>
            </summary>
            <div className="ux-axes">
              {scorecard.axes.map((a, i) => {
                const tv = s[target]?.[a.key];
                const rv = s[ref]?.[a.key];
                return (
                  <div key={a.key} className="ux-axis" title={a.question} style={{ "--d": `${i * 40}ms`, "--s": (tv ?? 0) / 10, "--r": (rv ?? 0) / 10 } as Vars}>
                    <span className="ux-axis-label">{a.label}</span>
                    <span className="ux-axis-bar">
                      <span className="ux-track-fill" />
                      {rv != null ? <span className="ux-track-ref" /> : null}
                    </span>
                    <span className="ux-axis-num">{tv ?? "—"}</span>
                  </div>
                );
              })}
              <p className="ux-axes-total">
                合計 {REGION_LABEL[target]} <b>{total(s[target]) ?? "—"}</b> / {REGION_LABEL[ref]} {total(s[ref]) ?? "—"}（各10点 → 100点換算）
              </p>
            </div>
            {imps.length ? (
              <ol className="ux-imps">
                {imps.map((m, i) => (
                  <li key={i}>
                    <b>{axisLabel[m.axis] || m.axis}</b>
                    <span className="ux-imp-next">{m.next}</span>
                    <span className="ux-imp-gap">比較相手との差：{m.gap}</span>
                  </li>
                ))}
              </ol>
            ) : null}
          </details>
        );
      })}

      <details className="ux-detail">
        <summary>
          <span>比較相手と項目ごとの基準</span>
        </summary>
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
