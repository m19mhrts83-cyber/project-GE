import Link from "next/link";
import Shell from "@/components/Shell";
import VpointAckButton from "@/components/VpointAckButton";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "vpoint";

type RateBucket = {
  rate_pct?: number | null;
  pt?: number | null;
  count?: number | null;
  samples?: { date?: string; desc?: string; pt?: number }[];
};

type GrantSummary = {
  target_month?: string | null;
  total_pt?: number | null;
  by_cadence?: {
    monthly?: number;
    daily?: number;
    other?: number;
  } | null;
  by_rate?: RateBucket[];
  insights?: string[];
  shop_up_ok?: boolean | null;
  condition_grants_ok?: boolean | null;
  source_note?: string | null;
  at?: string | null;
  grant_rule?: string | null;
};

type HistoryRow = {
  target_month?: string | null;
  total_pt?: number | null;
  by_cadence?: {
    monthly?: number;
    daily?: number;
    other?: number;
  } | null;
  insights?: string[];
  at?: string | null;
  source_note?: string | null;
};

function fmtPt(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n).toLocaleString("ja-JP")}pt`;
}

function fmtRate(n: number | null | undefined) {
  if (n == null) return "不明";
  return `${n}%`;
}

export default async function VpointPage() {
  const supabase = await createClient();
  const { data: watch } = await supabase
    .from("watch_status")
    .select("*")
    .eq("id", WATCH_ID)
    .maybeSingle();

  const payload =
    watch?.payload && typeof watch.payload === "object"
      ? (watch.payload as Record<string, unknown>)
      : {};

  const summary = (
    payload.grant_summary && typeof payload.grant_summary === "object"
      ? (payload.grant_summary as GrantSummary)
      : {}
  ) as GrantSummary;

  const history = Array.isArray(payload.grant_history)
    ? (payload.grant_history as HistoryRow[])
    : [];

  const ack =
    typeof payload.dashboard_ack_target_month === "string"
      ? payload.dashboard_ack_target_month
      : null;
  const target = summary.target_month || null;
  const hasGrant = target != null && summary.total_pt != null;
  const showBanner =
    typeof payload.show_banner === "boolean"
      ? payload.show_banner
      : Boolean(hasGrant && ack !== target);

  const bc = summary.by_cadence || {};
  const byRate = Array.isArray(summary.by_rate) ? summary.by_rate : [];
  const insights = Array.isArray(summary.insights) ? summary.insights : [];

  return (
    <Shell active="/vpoint">
      <h1>Vポイント</h1>
      <p className="sub">
        月次付与サマリ（日次利用／月次条件・％別）と考察。ウィンドウC（25日〜月末）に更新。
      </p>

      {showBanner && hasGrant ? (
        <article className="card level-info etc-rebate-banner">
          <header>
            <span className="lvl">付与</span>
            <strong>{target}分のポイント付与サマリ</strong>
          </header>
          <div className="etc-rebate-hero">
            <div>
              <span className="meta">合計</span>
              <strong className="etc-rebate-yen">{fmtPt(summary.total_pt)}</strong>
            </div>
            <div>
              <span className="meta">月次条件系</span>
              <strong>{fmtPt(bc.monthly ?? 0)}</strong>
            </div>
            <div>
              <span className="meta">日次・利用連動</span>
              <strong>{fmtPt(bc.daily ?? 0)}</strong>
            </div>
            <div>
              <span className="meta">その他</span>
              <strong>{fmtPt(bc.other ?? 0)}</strong>
            </div>
          </div>
          <p className="sum">
            {summary.grant_rule ||
              "ウィンドウC（25日〜月末）に月次サマリ更新。付与は日次利用と月次条件が混在"}
          </p>
          {summary.source_note ? (
            <p className="meta">{summary.source_note}</p>
          ) : null}

          {byRate.length > 0 ? (
            <div className="vpoint-rate-table-wrap">
              <h3 className="vpoint-subh">％別集計</h3>
              <table className="vpoint-rate-table">
                <thead>
                  <tr>
                    <th>還元率</th>
                    <th>ポイント</th>
                    <th>件数</th>
                    <th>代表</th>
                  </tr>
                </thead>
                <tbody>
                  {byRate.map((r, i) => (
                    <tr key={`${r.rate_pct ?? "u"}-${i}`}>
                      <td>{fmtRate(r.rate_pct)}</td>
                      <td>{fmtPt(r.pt)}</td>
                      <td>{r.count ?? "—"}</td>
                      <td className="meta">
                        {(r.samples || [])
                          .slice(0, 2)
                          .map((s) => s.desc || "")
                          .filter(Boolean)
                          .join(" / ") || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {insights.length > 0 ? (
            <div className="vpoint-insights">
              <h3 className="vpoint-subh">考察</h3>
              <ul className="etc-guide-list">
                {insights.map((ins, i) => (
                  <li key={i}>{ins}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <VpointAckButton targetMonth={target!} />
        </article>
      ) : hasGrant ? (
        <article className="card level-ok etc-rebate-banner is-acked">
          <header>
            <span className="lvl">確認済</span>
            <strong>{target}分は確認済み</strong>
          </header>
          <p className="sum">
            合計 {fmtPt(summary.total_pt)}
            {bc.monthly != null ? ` · 月次条件 ${fmtPt(bc.monthly)}` : ""}
            {bc.daily != null ? ` · 日次 ${fmtPt(bc.daily)}` : ""}
            。次の表示はウィンドウC更新後です。
          </p>
        </article>
      ) : (
        <article className="card">
          <p className="sum">
            まだ付与サマリがありません。毎月25日〜月末（ウィンドウC）に Tサイト履歴／監査から
            Jarvis が更新します。
          </p>
        </article>
      )}

      <section className="etc-guide" aria-label="凡例">
        <h2>日次 vs 月次条件</h2>
        <ul className="etc-guide-list">
          <li>
            <strong>月次条件系</strong> — 投信積立カード決済特典、選べる特典／給与特典、資産運用特典など（条件達成で月1回前後）
          </li>
          <li>
            <strong>日次・利用連動</strong> — 店名＋「＋N%」などの利用ポイント
          </li>
          <li>
            <strong>％の見方</strong> — desc の＋N% 優先。積立は pt÷積立円。yen があれば pt÷yen
          </li>
          <li>
            詳細突合: Literature Note §6.6 /{" "}
            <code>jarvis-vpoint-audit.mdc</code>
          </li>
        </ul>
      </section>

      <section>
        <h2>過去の付与</h2>
        {history.length === 0 && !hasGrant ? (
          <p className="empty">履歴はまだありません</p>
        ) : (
          <ul className="etc-history-list">
            {(history.length
              ? history
              : [
                  {
                    target_month: summary.target_month,
                    total_pt: summary.total_pt,
                    by_cadence: summary.by_cadence,
                    at: summary.at,
                    source_note: summary.source_note,
                  },
                ]
            ).map((h, i) => (
              <li key={`${h.target_month || "x"}-${i}`}>
                <strong>{h.target_month || "—"}</strong>
                {" · "}
                {fmtPt(h.total_pt)}
                {h.by_cadence ? (
                  <>
                    {" · 月次 "}
                    {fmtPt(h.by_cadence.monthly ?? 0)}
                    {" · 日次 "}
                    {fmtPt(h.by_cadence.daily ?? 0)}
                  </>
                ) : null}
                {h.at ? (
                  <span className="meta">
                    {" "}
                    · 更新 {String(h.at).slice(0, 10)}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="sub" style={{ marginTop: 16 }}>
        <Link href="/situation">状況ウォッチ →</Link>
        {" · "}
        <Link href="/metrics">収支・数値 →</Link>
      </p>
    </Shell>
  );
}
