import Shell from "@/components/Shell";
import QuietEdgeClient, {
  type SnoreRow,
} from "@/components/quiet-edge/QuietEdgeClient";
import SnoreTrendChart, {
  type SnorePoint,
} from "@/components/quiet-edge/SnoreTrendChart";
import { createClient } from "@/lib/supabase/server";

function fmtCount(n: number | null | undefined) {
  if (n == null) return "—";
  return `${n.toLocaleString("ja-JP")}回`;
}

function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return null;
  const now = Date.now();
  return Math.ceil((t - now) / (1000 * 60 * 60 * 24));
}

export default async function QuietEdgePage() {
  const supabase = await createClient();

  const { data: snoreRows } = await supabase
    .from("vital_snore_daily")
    .select("recorded_at,score,count,event,sleep_time,memo,source")
    .order("recorded_at", { ascending: true });

  const { data: treatments } = await supabase
    .from("vital_treatment_events")
    .select("session_no,scheduled_at,label,status,note")
    .order("session_no", { ascending: true });

  const rows = (snoreRows || []) as SnoreRow[];
  const chartPoints: SnorePoint[] = rows.map((r) => ({
    date: r.recorded_at,
    score: Number(r.score),
    count: r.count,
    event: r.event,
  }));

  const latest = rows.length ? rows[rows.length - 1] : null;
  const withCount = rows.filter((r) => r.count != null);
  const minScoreRow = rows.reduce<(typeof rows)[0] | null>((best, r) => {
    if (!best || r.score < best.score) return r;
    return best;
  }, null);

  const doneSessions = (treatments || []).filter((t) => t.status === "done");
  const nextSession = (treatments || []).find((t) => t.status === "scheduled");
  const totalPlanned = Math.max(9, (treatments || []).length);
  const progressPct = Math.round((doneSessions.length / totalPlanned) * 1000) / 10;
  const countdown = daysUntil(nextSession?.scheduled_at);

  const avgScore =
    rows.length > 0
      ? rows.reduce((s, r) => s + Number(r.score), 0) / rows.length
      : null;

  return (
    <Shell active="/quiet-edge">
      <h1>Quiet Edge</h1>
      <p className="sub">
        静音ロード — AutoSnore のいびき記録を長期保管し、レーザー治療の推移を見る。
        診断ではありません。医師に見せるための観察整理です。
      </p>

      <div className="qe-top-grid">
        <article className="card qe-banner">
          <header>
            <span className="lvl">経過</span>
            <strong>
              {latest
                ? `最新 ${latest.recorded_at}（スコア ${Number(latest.score).toFixed(1)} / ${fmtCount(latest.count)}）`
                : "まだ記録がありません"}
            </strong>
          </header>
          <p className="sum">
            毎朝 AutoSnore から「イビガースコア」と「検出回数」のスクショ2枚を取り込むと、30日失効後もここに残ります。
          </p>
        </article>

        <article className="card qe-countdown">
          <header>
            <span className="lvl">治療</span>
            <strong>
              {nextSession ? nextSession.label : "予定なし"}
            </strong>
          </header>
          <p className="qe-countdown-num">
            {countdown == null
              ? "—"
              : countdown >= 0
                ? `${countdown}日後`
                : `${Math.abs(countdown)}日前`}
          </p>
          <p className="meta">
            {nextSession?.scheduled_at
              ? new Date(nextSession.scheduled_at).toLocaleString("ja-JP", {
                  timeZone: "Asia/Tokyo",
                })
              : "—"}
          </p>
          <div className="qe-progress">
            <span>
              進行 {doneSessions.length}/{totalPlanned}（{progressPct}%）
            </span>
            <div className="qe-progress-bar">
              <i style={{ width: `${Math.min(100, progressPct)}%` }} />
            </div>
          </div>
        </article>
      </div>

      <div className="qe-kpi-grid">
        <article className="card">
          <p className="meta">直近スコア</p>
          <p className="qe-kpi">
            {latest ? Number(latest.score).toFixed(1) : "—"}
          </p>
          <p className="meta">
            平均 {avgScore != null ? avgScore.toFixed(1) : "—"}
          </p>
        </article>
        <article className="card">
          <p className="meta">直近回数</p>
          <p className="qe-kpi">{latest ? fmtCount(latest.count) : "—"}</p>
          <p className="meta">回数あり {withCount.length}日</p>
        </article>
        <article className="card">
          <p className="meta">最小スコア</p>
          <p className="qe-kpi">
            {minScoreRow ? Number(minScoreRow.score).toFixed(1) : "—"}
          </p>
          <p className="meta">
            {minScoreRow ? minScoreRow.recorded_at : "—"}
          </p>
        </article>
        <article className="card">
          <p className="meta">記録日数</p>
          <p className="qe-kpi">{rows.length}</p>
          <p className="meta">Canvas 移行込み</p>
        </article>
      </div>

      <article className="card">
        <header>
          <span className="lvl">推移</span>
          <strong>いびき改善プロセス</strong>
        </header>
        <SnoreTrendChart points={chartPoints} />
      </article>

      <article className="card">
        <header>
          <span className="lvl">スケジュール</span>
          <strong>レーザー治療タイムライン</strong>
        </header>
        <ul className="qe-timeline">
          {(treatments || []).map((t) => (
            <li key={t.session_no} data-status={t.status}>
              <strong>
                {t.label}
                <span className="meta">
                  {" "}
                  · {t.status === "done" ? "完了" : t.status === "scheduled" ? "予定" : t.status}
                </span>
              </strong>
              <p className="meta">
                {new Date(t.scheduled_at).toLocaleString("ja-JP", {
                  timeZone: "Asia/Tokyo",
                })}
              </p>
              {t.note ? <p className="sum">{t.note}</p> : null}
            </li>
          ))}
        </ul>
      </article>

      <QuietEdgeClient rows={rows} />
    </Shell>
  );
}
