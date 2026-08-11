import type { GluconMotivationStats } from "@/lib/glucon/stats";
import GluconTrendChart from "./GluconTrendChart";

const DOT_LABEL: Record<GluconMotivationStats["habitDots"][number]["state"], string> =
  {
    achieved: "達成",
    missed: "未達",
    pending: "今月",
    future: "未来",
  };

export default function GluconMotivationPanel({
  stats,
}: {
  stats: GluconMotivationStats;
}) {
  return (
    <section
      className="glucon-motivation"
      aria-labelledby="glucon-motivation-heading"
    >
      <h2 id="glucon-motivation-heading">継続とポイント</h2>
      <p className="meta">
        活動を投稿またはスキップした月を連続として数えます。ポイントは成果本文の目安です。運営採点の保証ではありません。
      </p>

      <div className="qe-kpi-grid glucon-kpi-grid">
        <article className="card">
          <p className="meta">現在の連続</p>
          <p className="qe-kpi">{stats.currentStreak}</p>
          <p className="meta">ヶ月</p>
        </article>
        <article className="card">
          <p className="meta">最長連続</p>
          <p className="qe-kpi">{stats.longestStreak}</p>
          <p className="meta">ヶ月</p>
        </article>
        <article className="card">
          <p className="meta">報告した月</p>
          <p className="qe-kpi">{stats.postedMonths}</p>
          <p className="meta">活動 posted / skipped</p>
        </article>
        <article className="card">
          <p className="meta">目安ポイント累計</p>
          <p className="qe-kpi">{stats.estimatedPointsTotal}</p>
          <p className="meta">成果の自己チェック</p>
        </article>
      </div>

      <div className="glucon-habit" aria-label="直近12ヶ月の達成">
        {stats.habitDots.map((dot) => (
          <span
            key={dot.periodKey}
            className={`glucon-habit-dot state-${dot.state}`}
            title={`${dot.periodKey} ${DOT_LABEL[dot.state]}`}
          >
            <i />
            <em>{dot.periodKey.slice(5)}</em>
          </span>
        ))}
      </div>

      <GluconTrendChart points={stats.trend} mode="frequency" />
      <GluconTrendChart points={stats.trend} mode="points" />
    </section>
  );
}
