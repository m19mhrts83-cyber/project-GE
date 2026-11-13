import { axisLevel, goalAt, loadSnapshots, maturityConfig, priorities } from "@/lib/agentMaturity";

/** ホームの「AIエージェント運用」要約。詳細と Todoist ボタンは /agent-team#maturity */
export default async function HomeMaturityBand() {
  const { team } = await loadSnapshots(8);
  const latest = team[team.length - 1] ?? null;
  const prev = team.length > 1 ? team[team.length - 2] : null;
  const goal = goalAt(new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" }).format(new Date()));

  return (
    <article className="card mat-band" style={{ marginBottom: 16 }}>
      <header>
        <span className="lvl">AI運用</span>
        <strong>AIエージェント運用の成熟度</strong>
        {latest ? <span className="meta">{latest.measured_on} 計測</span> : null}
      </header>
      {!latest ? (
        <p className="sum">まだ計測の記録がありません。毎週土曜に自動で計測します。</p>
      ) : (
        <>
          <p className="sum mat-band-axes">
            {maturityConfig.axes.map((axis) => {
              const a = axisLevel(axis, latest);
              const p = prev ? axisLevel(axis, prev).level : null;
              return (
                <span key={axis.key} className="mat-band-axis">
                  {axis.key === "process" ? "Process" : "Output"}{" "}
                  <b>{a.level == null ? "未計測" : `L${a.level}`}</b>
                  {goal ? <span className="meta"> / 目標 L{goal[axis.key]}</span> : null}
                  {p != null && a.level != null && a.level !== p ? (
                    <span className={`mat-delta ${a.level > p ? "up" : "down"}`}> {a.level > p ? "+" : ""}{Math.round((a.level - p) * 10) / 10}</span>
                  ) : null}
                  <span className="meta">（{a.measured}/{a.total}項目を計測）</span>
                </span>
              );
            })}
          </p>
          <p className="sum mat-band-prio">
            優先改善：{priorities(latest, prev).map((p) => `${p.item.label}${p.level == null ? "（未計測）" : `（L${p.level}）`}`).join("、")}
          </p>
        </>
      )}
      <a className="btn" href="/agent-team#maturity" style={{ marginTop: 10 }}>
        成熟度の詳細と改善 →
      </a>
    </article>
  );
}
