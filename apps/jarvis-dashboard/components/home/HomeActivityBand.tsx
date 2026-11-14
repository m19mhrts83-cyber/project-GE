import MaturityCountUp from "@/components/agent-team/MaturityCountUp";
import { SIGNAL_LABEL, SIGNAL_ORDER, loadWeeklyActivity, md } from "@/lib/agentWeeklyActivity";

/** ホームの「AI社員の週次稼働」要約。詳細は /agent-team#activity（土曜 9:00 集計） */
export default async function HomeActivityBand() {
  const { report } = await loadWeeklyActivity();

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
      <a className="btn" href="/agent-team#activity" style={{ marginTop: 10 }}>
        社員ごとの稼働を見る →
      </a>
    </article>
  );
}
