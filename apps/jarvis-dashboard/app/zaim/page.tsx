import Link from "next/link";
import Shell from "@/components/Shell";
import FolderLinks from "@/components/FolderLinks";
import StatusToggle from "@/components/StatusToggle";
import WatchCommentThread, {
  type WatchCommentRow,
} from "@/components/WatchCommentThread";
import ZaimFixActions from "@/components/ZaimFixActions";
import ZaimReviewAckButton from "@/components/ZaimReviewAckButton";
import { LEVEL_LABEL, HomeLevel } from "@/lib/homeLevels";
import { getFolderLinks, pageFolderKey } from "@/lib/folderLinks";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "zaim_quality";

type ActionItem = {
  date?: string;
  shop?: string;
  amount?: number;
  proposal?: string;
  line?: string;
};

type FixItem = {
  id?: string;
  date?: string;
  shop?: string;
  amount?: number;
  proposal?: string;
  status?: string;
  value?: string;
  message?: string;
  applied_at?: string;
  batch_id?: string;
  learn_key?: string;
};

function isVisibleLearnFix(
  f: FixItem,
  ackBatchId: string,
  reviewBatchId: string,
): boolean {
  const st = f.status || "pending_confirm";
  if (st === "confirmed" || st === "failed") return false;
  if (st !== "pending_confirm" && st !== "disputed") return false;
  const bid = String(f.batch_id || reviewBatchId || "");
  if (ackBatchId && bid && ackBatchId === bid) return false;
  return true;
}

function fmtYen(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n).toLocaleString("ja-JP")}円`;
}

function isYmdDate(raw: string | undefined): boolean {
  return Boolean(raw && /^\d{4}-\d{2}-\d{2}$/.test(raw));
}

function yearMonthParts(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(now);
  const y = Number(parts.find((p) => p.type === "year")?.value);
  const m = Number(parts.find((p) => p.type === "month")?.value);
  return { y, m };
}

function sumYear(
  latest: Map<string, number>,
  year: number,
  entity: string,
  metric: string,
  maxMonth = 12,
): { total: number; months: number } {
  let total = 0;
  let months = 0;
  for (let mo = 1; mo <= maxMonth; mo++) {
    const ym = `${year}-${String(mo).padStart(2, "0")}`;
    const v = latest.get(`${ym}|${entity}|${metric}`);
    if (v != null) {
      total += v;
      months += 1;
    }
  }
  return { total, months };
}

export default async function ZaimWatchPage() {
  const supabase = await createClient();
  const { y: thisYear, m: thisMonth } = yearMonthParts();
  const lastYear = thisYear - 1;

  const [{ data: watch }, { data: metricRows }, { data: comments }] =
    await Promise.all([
      supabase.from("watch_status").select("*").eq("id", WATCH_ID).maybeSingle(),
      supabase
        .from("metrics")
        .select("metric,entity,value,recorded_at")
        .in("metric", ["income_total", "expense_total", "cashflow"])
        .in("entity", ["corporate", "personal"])
        .gte("recorded_at", `${lastYear}-01-01`)
        .lte("recorded_at", `${thisYear}-12-31`)
        .limit(800),
      supabase
        .from("watch_comments")
        .select("id,watch_id,role,body,created_at")
        .eq("watch_id", WATCH_ID)
        .order("created_at", { ascending: true }),
    ]);

  const latest = new Map<string, number>();
  for (const r of metricRows || []) {
    const ym = String(r.recorded_at).slice(0, 7);
    const key = `${ym}|${r.entity}|${r.metric}`;
    if (!latest.has(key)) latest.set(key, Number(r.value));
  }

  const annual = [lastYear, thisYear].map((year) => {
    const maxM = year === thisYear ? thisMonth : 12;
    const corpIn = sumYear(latest, year, "corporate", "income_total", maxM);
    const corpEx = sumYear(latest, year, "corporate", "expense_total", maxM);
    const perIn = sumYear(latest, year, "personal", "income_total", maxM);
    const perEx = sumYear(latest, year, "personal", "expense_total", maxM);
    const income = corpIn.total + perIn.total;
    const expense = corpEx.total + perEx.total;
    return {
      year,
      label:
        year === thisYear
          ? `${year}年（〜${thisMonth}月・YTD）`
          : `${year}年（通年）`,
      income,
      expense,
      net: income - expense,
      months: Math.max(corpIn.months, perIn.months, corpEx.months, perEx.months),
      corporate: {
        income: corpIn.total,
        expense: corpEx.total,
        net: corpIn.total - corpEx.total,
      },
      personal: {
        income: perIn.total,
        expense: perEx.total,
        net: perIn.total - perEx.total,
      },
    };
  });

  const payload =
    watch?.payload && typeof watch.payload === "object"
      ? (watch.payload as Record<string, unknown>)
      : {};
  const actions = Array.isArray(payload.actions)
    ? (payload.actions as ActionItem[])
    : [];
  const fixes = Array.isArray(payload.recent_fixes)
    ? (payload.recent_fixes as FixItem[])
    : [];
  const reviewBatchId = String(payload.review_batch_id || "");
  const ackBatchId = String(payload.dashboard_ack_batch_id || "");
  const visibleFixes = fixes.filter((f) =>
    isVisibleLearnFix(f, ackBatchId, reviewBatchId),
  );
  const otherFixes = fixes.filter(
    (f) => !isVisibleLearnFix(f, ackBatchId, reviewBatchId),
  );
  const showBanner = payload.show_banner === true || visibleFixes.length > 0;
  const reviewLines = Array.isArray(payload.review_lines)
    ? (payload.review_lines as string[])
    : [];
  const categoryReviews = Array.isArray(payload.category_reviews)
    ? (payload.category_reviews as {
        date?: string;
        shop?: string;
        amount?: number;
        proposal?: string;
        category?: string;
        suggest?: string;
        confidence?: string;
      }[])
    : [];
  const learnFb =
    payload.learn_feedback && typeof payload.learn_feedback === "object"
      ? (payload.learn_feedback as {
          learned_n?: number;
          ready_auto_n?: number;
          rule_count?: number;
          examples?: { shop?: string; from?: string; to?: string; learn_key?: string }[];
          ready_examples?: { key?: string; category?: string; count?: number }[];
        })
      : null;
  const neverArchive = Boolean(payload.never_archive);
  const level = (
    ["attention", "warn", "info", "ok"].includes(watch?.level || "")
      ? watch?.level
      : "info"
  ) as HomeLevel | "ok";
  const label =
    level === "ok" ? "OK" : LEVEL_LABEL[level as HomeLevel] || level;

  const commentRows: WatchCommentRow[] = (comments || []).map((c) => ({
    id: c.id,
    role: c.role,
    body: c.body,
    created_at: c.created_at,
  }));
  const folderLinks = getFolderLinks(pageFolderKey("zaim"));

  return (
    <Shell active="/zaim">
      <h1>Zaim Watch</h1>
      <FolderLinks links={folderLinks} />
      <p className="sub">
        財務の年間収支と、集計設定・二重取込・費目の学習結果。アーカイブせず常駐します。
        確信度の高い直しは Jarvis が財務側へ適用し、結果をここに残します（確認したまで消えません）。
        修正は Zaim 本体で行い、次の取込で学習します。学習が違うときだけ「おかしい」で印を付けます。
        火・金に見直し（CSV は同曜日）。年間収支は Zaim の「集計に含めない」を除外した合計です（当年は1〜当月の
        YTD）。詳細な月次は{" "}
        <Link href="/metrics" style={{ color: "var(--accent)", fontWeight: 600 }}>
          収支・数値
        </Link>
        。
      </p>

      {showBanner || visibleFixes.length > 0 ? (
        <section className="card level-attention" style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">お知らせ</span>
            <strong>Jarvisが直したよ（財務）</strong>
          </header>
          <ul className="openchat-group-lines">
            {(reviewLines.length
              ? reviewLines
              : visibleFixes.length
                ? [`学習・修正 ${visibleFixes.length}件（未確認）`]
                : ["見直し結果があります"]
            ).map((ln, i) => (
              <li key={i}>{ln}</li>
            ))}
          </ul>
          <p className="meta" style={{ marginBottom: 8 }}>
            修正は財務（Zaim）側。ここは結果の確認と、学習ミスの印です。「確認した」でピンと一覧を消します。新しい修正が出たらまた表示されます。
          </p>
          <ZaimReviewAckButton batchId={reviewBatchId} />
        </section>
      ) : null}

      <section className="card" style={{ marginBottom: 16 }}>
        <header>
          <strong>年間収支</strong>
          <span className="meta">法人＋個人 · Supabase metrics</span>
        </header>
        <div className="zaim-annual-grid">
          {annual.map((a) => (
            <div key={a.year} className="zaim-annual-col">
              <p className="zaim-annual-label">{a.label}</p>
              <p className="sum">
                収入 <strong>{fmtYen(a.income)}</strong>
              </p>
              <p className="sum">
                支出 <strong>{fmtYen(a.expense)}</strong>
              </p>
              <p className="sum">
                差額 <strong>{fmtYen(a.net)}</strong>
              </p>
              <p className="meta">
                データ月 {a.months || 0} · 法人 {fmtYen(a.corporate.net)} / 個人{" "}
                {fmtYen(a.personal.net)}
              </p>
            </div>
          ))}
        </div>
        {annual.every((a) => a.months === 0) ? (
          <p className="empty" style={{ marginTop: 8 }}>
            メトリクス未 push。CSV 週次または jarvis_finance_metrics.py --push
            後に表示されます。
          </p>
        ) : null}
      </section>

      <article className={`card level-${watch?.level || "info"}`}>
        <header>
          <span className="lvl">{label}</span>
          <strong>{watch?.title || "Zaim Watch"}</strong>
          <span className="meta">{watch?.source || "—"}</span>
          {!neverArchive && watch ? (
            <StatusToggle
              table="watch_status"
              id={WATCH_ID}
              status={watch.status || "active"}
              path="/zaim"
            />
          ) : (
            <span className="meta" style={{ marginLeft: "auto" }}>
              常駐（アーカイブ不可）
            </span>
          )}
        </header>
        <p className="sum">{watch?.summary || "まだ push されていません"}</p>

        {actions.length > 0 ? (
          <div className="watch-actions">
            <p className="watch-actions-title">要対応（未適用・要判断）</p>
            <ul>
              {actions.map((a, idx) => (
                <li key={`${a.date}-${a.shop}-${idx}`}>
                  {isYmdDate(a.date) ? (
                    <span className="watch-action-date">{a.date}</span>
                  ) : null}
                  <span className="watch-action-shop">{a.shop || "—"}</span>
                  {a.amount != null ? (
                    <span className="watch-action-yen">{fmtYen(a.amount)}</span>
                  ) : null}
                  <span className="watch-action-proposal">
                    {a.proposal || a.line || "—"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {learnFb ? (
          <div className="watch-actions" style={{ marginTop: 12 }}>
            <p className="watch-actions-title">学習フィードバック</p>
            <p className="meta">
              前回の手動差分 {learnFb.learned_n ?? 0} 件 · ルール{" "}
              {learnFb.rule_count ?? 0} · 次回から自動{" "}
              {learnFb.ready_auto_n ?? 0} 件
            </p>
            {(learnFb.examples || []).length > 0 ? (
              <ul>
                {(learnFb.examples || []).slice(0, 5).map((ex, idx) => (
                  <li key={`learn-${idx}`}>
                    <span className="watch-action-shop">
                      {ex.shop || ex.learn_key || "—"}
                    </span>
                    <span className="watch-action-proposal">
                      {ex.from || "?"} → {ex.to || "?"}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="meta">今回の新規学習はありません</p>
            )}
            {(learnFb.ready_examples || []).length > 0 ? (
              <p className="meta" style={{ marginTop: 6 }}>
                自動候補:{" "}
                {(learnFb.ready_examples || [])
                  .slice(0, 4)
                  .map((r) => `${r.key || "?"}→${r.category || "?"}`)
                  .join(" / ")}
              </p>
            ) : null}
          </div>
        ) : null}

        {categoryReviews.length > 0 ? (
          <div className="watch-actions">
            <p className="watch-actions-title">費目見直し（提案・未自動変更）</p>
            <ul>
              {categoryReviews.slice(0, 20).map((c, idx) => (
                <li key={`${c.date}-${c.shop}-${idx}`}>
                  {isYmdDate(c.date) ? (
                    <span className="watch-action-date">{c.date}</span>
                  ) : null}
                  <span className="watch-action-shop">{c.shop || "—"}</span>
                  {c.amount != null ? (
                    <span className="watch-action-yen">{fmtYen(c.amount)}</span>
                  ) : null}
                  <span className="watch-action-proposal">
                    {c.proposal || c.category || "—"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {visibleFixes.length > 0 ? (
          <div className="watch-actions">
            <p className="watch-actions-title">学習・修正された内容</p>
            <ul>
              {visibleFixes.map((f, idx) => (
                <li
                  key={`${f.id}-${idx}`}
                  className="watch-action-stack"
                  style={{ alignItems: "flex-start" }}
                >
                  <div style={{ flex: 1 }}>
                    {isYmdDate(f.date) ? (
                      <span className="watch-action-date">{f.date} </span>
                    ) : null}
                    <span className="watch-action-shop">{f.shop || "—"}</span>
                    {f.amount != null ? (
                      <span className="watch-action-yen">
                        {" "}
                        {fmtYen(f.amount)}
                      </span>
                    ) : null}
                    <div className="watch-action-proposal">
                      {f.proposal || "—"}
                    </div>
                  </div>
                  {f.id ? (
                    <ZaimFixActions
                      fixId={String(f.id)}
                      flagged={f.status === "disputed"}
                      path="/zaim"
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="meta" style={{ marginTop: 8 }}>
            未確認の学習・修正はありません
          </p>
        )}

        {otherFixes.length > 0 ? (
          <details className="watch-prompt-details">
            <summary>確認後の履歴（confirmed / failed など・{otherFixes.length}）</summary>
            <ul className="watch-actions" style={{ listStyle: "none", padding: 0 }}>
              {otherFixes
                .slice()
                .reverse()
                .map((f, idx) => (
                  <li key={`${f.id}-done-${idx}`} style={{ marginBottom: 6 }}>
                    <span className="meta">[{f.status}] </span>
                    {f.proposal || f.id}
                  </li>
                ))}
            </ul>
          </details>
        ) : null}

        {watch?.detail ? (
          <details className="watch-prompt-details">
            <summary>詳細・銀行連携メモ</summary>
            <pre className="watch-detail">{watch.detail}</pre>
          </details>
        ) : null}

        <WatchCommentThread
          watchId={WATCH_ID}
          title={watch?.title || "Zaim Watch"}
          summary={watch?.summary}
          detail={watch?.detail}
          cursorPrompt={watch?.cursor_prompt}
          payload={
            watch?.payload && typeof watch.payload === "object"
              ? (watch.payload as Record<string, unknown>)
              : null
          }
          comments={commentRows}
          path="/zaim"
        />
      </article>
    </Shell>
  );
}
