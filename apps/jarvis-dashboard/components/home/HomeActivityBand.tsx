import MaturityCountUp from "@/components/agent-team/MaturityCountUp";
import { SIGNAL_LABEL, SIGNAL_ORDER, loadWeeklyActivity, md } from "@/lib/agentWeeklyActivity";
import { loadStageReview } from "@/lib/agentStageReview";

/** ホームの「AI社員の週次稼働」要約。詳細は /agent-team#activity（土曜 9:00 集計） */
export default async function HomeActivityBand() {
  const [{ report }, { review: stage, decided }] = await Promise.all([loadWeeklyActivity(), loadStageReview()]);
  const open = stage ? stage.proposals.filter((p) => !decided[p.key]) : [];

  return (
    <article className="card wa-band" style={{ marginBottom: 16 }}>
      <header>
        <span className="lvl">AI運用</span>
        <strong>AI社員の週次稼働</strong>
        {report ? <span className="meta">{md(report.since)}〜{md(report.until)} 集計</span> : null}
      </header>
      {!report ? (
        <p className="sum">まだ集計の記録がありません。毎週土曜 9:00 に、各AI社員・Grok Bot がどれだけ機能したかを数えます。</p>
      ) : (
        <>
          <p className="sum wa-band-main">
            今週機能した社員{" "}
            <b className="wa-band-big">
              <MaturityCountUp value={report.worked_agents} decimals={0} />
            </b>
            <span className="meta"> / {report.total_agents}</span>
            <span className="wa-band-sigs">
              {SIGNAL_ORDER.map((k) => (
                <span key={k} title={SIGNAL_LABEL[k]}>
                  {k}
                  {report.summary[k] ?? 0}
                </span>
              ))}
            </span>
          </p>
          {report.attention.length ? (
            <ul className="wa-band-list">
              {report.attention.slice(0, 3).map((a) => (
                <li key={a.id}>
                  {a.signal} <b>{a.id.replace("grok:", "Grok ")}</b> {a.name}：{a.why}
                </li>
              ))}
              {report.attention.length > 3 ? <li className="meta">ほか {report.attention.length - 3} 件</li> : null}
            </ul>
          ) : (
            <p className="sum meta">止まっている・詰まっている社員はいません。</p>
          )}
        </>
      )}
      {stage ? (
        <p className="sum wa-band-stage">
          段階: 設計中 {stage.counts["設計中"] ?? 0}・運用確認 {stage.counts["運用確認"] ?? 0}・運用 {stage.counts["運用"] ?? 0}
          {open.length ? (
            <>
              {" "}
              ／ <a href="/review#stage">決めてほしい提案 {open.length} 件（{open.slice(0, 2).map((p) => `${p.id}→${p.to}`).join("・")}）</a>
            </>
          ) : (
            "／今週の提案なし"
          )}
        </p>
      ) : null}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
        <a className="btn" href="/agent-team#activity">
          社員ごとの稼働を見る →
        </a>
        {open.length ? (
          <a className="btn primary" href="/review#stage">
            段階の提案を決める →
          </a>
        ) : null}
      </div>
    </article>
  );
}
