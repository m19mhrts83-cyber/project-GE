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
  defaultMonthlyReviewYm,
  enrichSnoreChartEvents,
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
  /** 月次レビュー既定: 先月（JST） */
  const monthlyYm = defaultMonthlyReviewYm();

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
      .eq("period_key", monthlyYm)
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);

  const rows = (snoreRows || []) as SnoreRow[];
  const vitalRows = (healthRows || []) as VitalDailyRow[];
  const journals = (journalRows || []) as JournalDailyRow[];
  const notes = (noteRows || []) as ContextNoteRow[];
  const chartPoints: SnorePoint[] = enrichSnoreChartEvents(
    rows.map((r) => ({
      date: r.recorded_at,
      score: Number(r.score),
      count: r.count,
      event: r.event,
    })),
    (treatments || []).map((t) => ({
      scheduled_at: t.scheduled_at,
      status: t.status,
    })),
    2,
  );

  const asks = buildQuietEdgeAsks({
    journals,
    notes,
    snore: rows.map((r) => ({
      recorded_at: r.recorded_at,
      score: Number(r.score),
      count: r.count,
    })),
    vitals: vitalRows.map((v) => ({
      recorded_at: v.recorded_at,
      metric: v.metric,
      value: Number(v.value),
      source: v.source,
    })),
    treatments: (treatments || []).map((t) => ({
      session_no: t.session_no,
      scheduled_at: t.scheduled_at,
      status: t.status,
      label: t.label,
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
  const nextSession =
    (treatments || []).find((t) => t.status === "scheduled") ||
    (treatments || []).find((t) => t.status === "planned");
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
        いびきレーザー治療の経過観察 — AutoSnore の長期保管と治療スケジュール。
        睡眠・SpO2 は治療連動の要約のみ。日中の仕事・運動は別ページ。診断ではありません。
      </p>
      <p className="meta">
        からだナビ: Quiet Edge（いびき）／
        <a href="/performance/work">仕事</a>／
        <a href="/performance/move">運動</a>
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
        initialYm={monthlyYm}
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
              : nextSession
                ? "日程未定"
                : "次回はチャットで Jarvis に伝えて更新"}
          </p>
          <div className="qe-progress">
            <span>
              進行 {doneSessions.length}/{totalPlanned}（総{totalPlanned}回目安・
              {progressPct}%）
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

      <QuietEdgeHealthBand rows={vitalRows} windowDays={14} compact />

      <QuietEdgeJournalBand
        journals={journals}
        snore={rows.map((r) => ({
          recorded_at: r.recorded_at,
          score: Number(r.score),
          count: r.count,
        }))}
        vitals={vitalRows.map((v) => ({
          recorded_at: v.recorded_at,
          metric: v.metric,
          value: Number(v.value),
          source: v.source,
        }))}
        windowDays={14}
        sleepFocus
      />

      <article className="card">
        <header>
          <span className="lvl">スケジュール</span>
          <strong>レーザー治療タイムライン</strong>
        </header>
        <p className="meta">
          総回数の目安は最大9回（経過を見て判断）。日程更新はアプリ入力せず、Jarvis
          に「第N回を〇月〇日」と伝えるだけで反映します。
        </p>
        <ul className="qe-timeline">
          {(treatments || []).map((t) => (
            <li key={t.session_no} data-status={t.status}>
              <strong>
                {t.label}
                <span className="meta">
                  {" "}
                  ·{" "}
                  {t.status === "done"
                    ? "完了"
                    : t.status === "scheduled"
                      ? "予定"
                      : t.status === "planned"
                        ? "枠（日程未定）"
                        : t.status === "cancelled"
                          ? "中止"
                          : t.status}
                </span>
              </strong>
              <p className="meta">
                {t.scheduled_at
                  ? new Date(t.scheduled_at).toLocaleString("ja-JP", {
                      timeZone: "Asia/Tokyo",
                    })
                  : "日程未定"}
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
