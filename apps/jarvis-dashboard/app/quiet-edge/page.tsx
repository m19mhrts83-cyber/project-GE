import Shell from "@/components/Shell";
import QuietEdgeAskPanel from "@/components/quiet-edge/QuietEdgeAskPanel";
import QuietEdgeClient, {
  type SnoreRow,
} from "@/components/quiet-edge/QuietEdgeClient";
import QuietEdgeHealthBand, {
  type VitalDailyRow,
} from "@/components/quiet-edge/QuietEdgeHealthBand";
import QuietEdgeJournalBand from "@/components/quiet-edge/QuietEdgeJournalBand";
import QuietEdgeLatestReview from "@/components/quiet-edge/QuietEdgeLatestReview";
import QuietEdgeMonthlyReview from "@/components/quiet-edge/QuietEdgeMonthlyReview";
import QuietEdgeReviewPanel from "@/components/quiet-edge/QuietEdgeReviewPanel";
import SnoreTrendChart, {
  SNORE_SCORE_TARGET,
  type SnorePoint,
} from "@/components/quiet-edge/SnoreTrendChart";
import {
  buildQuietEdgeAsks,
  addDaysYmd,
  ymdJst,
  type ContextNoteRow,
  type JournalDailyRow,
} from "@/lib/quietEdgeContext";
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
  const currentYm = ymdJst().slice(0, 7);

  const [
    { data: snoreRows },
    { data: treatments },
    { data: healthRows },
    { data: journalRows },
    { data: noteRows },
    { data: latestIngest },
    { data: latestMonthly },
  ] = await Promise.all([
    supabase
      .from("vital_snore_daily")
      .select("recorded_at,score,count,event,sleep_time,memo,source")
      .order("recorded_at", { ascending: true }),
    supabase
      .from("vital_treatment_events")
      .select("session_no,scheduled_at,label,status,note")
      .order("session_no", { ascending: true }),
    supabase
      .from("vital_daily")
      .select("recorded_at,metric,value,unit,source")
      .gte("recorded_at", addDaysYmd(ymdJst(), -20))
      .order("recorded_at", { ascending: true }),
    supabase
      .from("vital_journal_daily")
      .select("recorded_at,excerpt,char_count,source,sleep_signal,sleep_tags")
      .gte("recorded_at", addDaysYmd(ymdJst(), -20))
      .order("recorded_at", { ascending: false }),
    supabase
      .from("vital_context_notes")
      .select("id,recorded_at,trigger,prompt,answer,source,created_at")
      .gte("recorded_at", addDaysYmd(ymdJst(), -20))
      .order("created_at", { ascending: false })
      .limit(40),
    supabase
      .from("vital_quiet_reviews")
      .select("period_key,title,body,created_at")
      .eq("kind", "ingest")
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("vital_quiet_reviews")
      .select("period_key,title,body,created_at")
      .eq("kind", "monthly")
      .eq("period_key", currentYm)
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);

  const rows = (snoreRows || []) as SnoreRow[];
  const vitalRows = (healthRows || []) as VitalDailyRow[];
  const journals = (journalRows || []) as JournalDailyRow[];
  const notes = (noteRows || []) as ContextNoteRow[];
  const chartPoints: SnorePoint[] = rows.map((r) => ({
    date: r.recorded_at,
    score: Number(r.score),
    count: r.count,
    event: r.event,
  }));

  const asks = buildQuietEdgeAsks({
    journals,
    notes,
    snore: rows.map((r) => ({
      recorded_at: r.recorded_at,
      score: Number(r.score),
      count: r.count,
    })),
    windowDays: 14,
    maxAsks: 5,
  });

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
        Journal と月次レビューで生活要因を重ねる。診断ではありません。
      </p>

      {/* 1. 直近の取込 Gemini レビュー（最上部） */}
      <QuietEdgeLatestReview
        initial={
          latestIngest
            ? {
                period_key: latestIngest.period_key,
                title: latestIngest.title,
                body: latestIngest.body,
                created_at: latestIngest.created_at,
              }
            : null
        }
      />

      <article className="card qe-chart-hero">
        <header>
          <span className="lvl">推移</span>
          <strong>いびき改善プロセス</strong>
        </header>
        <SnoreTrendChart points={chartPoints} />
      </article>

      {/* 取込フロー（ログ表は末尾） */}
      <QuietEdgeClient rows={rows} sections={["upload", "form"]} />

      {/* 2. 月次レビュー（取込とログのあいだ） */}
      <QuietEdgeMonthlyReview
        currentYm={currentYm}
        initial={
          latestMonthly
            ? {
                period_key: latestMonthly.period_key,
                title: latestMonthly.title,
                body: latestMonthly.body,
                created_at: latestMonthly.created_at,
              }
            : null
        }
      />

      <div className="qe-top-grid">
        <article className="card qe-banner">
          <header>
            <span className="lvl">経過</span>
            <strong>
              {latest
                ? `最新 ${latest.recorded_at}（いびきスコア ${Number(latest.score).toFixed(1)} / いびき回数 ${fmtCount(latest.count)}）`
                : "まだ記録がありません"}
            </strong>
          </header>
          <p className="sum">
            毎朝 AutoSnore から「いびきスコア」と「いびき回数」のスクショ2枚を取り込むと、30日失効後もここに残ります。
            改善目標の目安はいびきスコア ≤ {SNORE_SCORE_TARGET}（観察用）。
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
          <p className="meta">直近いびきスコア</p>
          <p className="qe-kpi">
            {latest ? Number(latest.score).toFixed(1) : "—"}
          </p>
          <p className="meta">
            平均 {avgScore != null ? avgScore.toFixed(1) : "—"} ／ 目標 ≤
            {SNORE_SCORE_TARGET}
          </p>
        </article>
        <article className="card">
          <p className="meta">直近いびき回数</p>
          <p className="qe-kpi">{latest ? fmtCount(latest.count) : "—"}</p>
          <p className="meta">回数あり {withCount.length}日</p>
        </article>
        <article className="card">
          <p className="meta">最小いびきスコア</p>
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
          <p className="meta">Journal {journals.length}日分</p>
        </article>
      </div>

      <QuietEdgeHealthBand rows={vitalRows} windowDays={14} />

      <QuietEdgeJournalBand
        journals={journals}
        snore={rows.map((r) => ({
          recorded_at: r.recorded_at,
          score: Number(r.score),
          count: r.count,
        }))}
        windowDays={14}
      />

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

      <details className="qe-fold">
        <summary>
          <span className="lvl">補完</span>
          <strong>何がありましたか？（必要なときだけ）</strong>
        </summary>
        <p className="meta qe-fold-hint">
          日常の観察は上の月次レビューが主線です。欠落や急変のときだけ開いてください。
        </p>
        <QuietEdgeAskPanel asks={asks} notes={notes} />
      </details>

      <details className="qe-fold">
        <summary>
          <span className="lvl">Review</span>
          <strong>横断観察レビュー（任意）</strong>
        </summary>
        <QuietEdgeReviewPanel />
      </details>

      {/* 3. ログ表は最後（長いので普段は下） */}
      <QuietEdgeClient rows={rows} sections={["log"]} />
    </Shell>
  );
}
