import Link from "next/link";
import Shell from "@/components/Shell";
import EtcAckButton from "@/components/EtcAckButton";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "etc_mileage";

type RebateSummary = {
  target_month?: string | null;
  rebate_yen?: number | null;
  asayu_trip_count?: number | null;
  asayu_rate_pct?: number | null;
  savings_yen?: number | null;
  approx_days?: number | null;
  at?: string | null;
  note?: string | null;
  grant_rule?: string | null;
};

type HistoryRow = {
  target_month?: string | null;
  rebate_yen?: number | null;
  asayu_trip_count?: number | null;
  asayu_rate_pct?: number | null;
  savings_yen?: number | null;
  at?: string | null;
  note?: string | null;
};

function fmtYen(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n).toLocaleString("ja-JP")}円`;
}

function fmtRate(n: number | null | undefined) {
  if (n == null) return "—";
  return `約${n}%`;
}

export default async function EtcPage() {
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
    payload.rebate_summary && typeof payload.rebate_summary === "object"
      ? (payload.rebate_summary as RebateSummary)
      : {}
  ) as RebateSummary;

  const history = Array.isArray(payload.rebate_history)
    ? (payload.rebate_history as HistoryRow[])
    : [];

  const ack =
    typeof payload.dashboard_ack_target_month === "string"
      ? payload.dashboard_ack_target_month
      : null;
  const target = summary.target_month || null;
  const hasRebate = target != null && summary.rebate_yen != null;
  const showBanner =
    typeof payload.show_banner === "boolean"
      ? payload.show_banner
      : Boolean(hasRebate && ack !== target);

  return (
    <Shell active="/etc">
      <h1>ETC</h1>
      <p className="sub">
        平日朝夕割引の還元サマリ（月1更新）と、伊勢湾岸など通勤向けの申請案内。
      </p>

      {showBanner && hasRebate ? (
        <article className="card level-info etc-rebate-banner">
          <header>
            <span className="lvl">還元</span>
            <strong>{target}分の還元が確定しています</strong>
          </header>
          <div className="etc-rebate-hero">
            <div>
              <span className="meta">還元額</span>
              <strong className="etc-rebate-yen">
                {fmtYen(summary.rebate_yen)}
              </strong>
            </div>
            <div>
              <span className="meta">対象回数</span>
              <strong>
                {summary.asayu_trip_count != null
                  ? `${summary.asayu_trip_count}回`
                  : "未取得"}
              </strong>
              {summary.approx_days != null ? (
                <span className="meta">
                  {" "}
                  （目安 {summary.approx_days}日分）
                </span>
              ) : null}
            </div>
            <div>
              <span className="meta">還元率</span>
              <strong>{fmtRate(summary.asayu_rate_pct)}</strong>
            </div>
            <div>
              <span className="meta">お得額</span>
              <strong>
                {fmtYen(
                  summary.savings_yen != null
                    ? summary.savings_yen
                    : summary.rebate_yen,
                )}
              </strong>
            </div>
          </div>
          <p className="sum">
            {summary.grant_rule ||
              "利用月の翌月20日にETCマイレージへ還元額付与"}
          </p>
          {summary.note ? <p className="meta">{summary.note}</p> : null}
          <EtcAckButton targetMonth={target!} />
        </article>
      ) : hasRebate ? (
        <article className="card level-ok etc-rebate-banner is-acked">
          <header>
            <span className="lvl">確認済</span>
            <strong>{target}分は確認済み</strong>
          </header>
          <p className="sum">
            還元 {fmtYen(summary.rebate_yen)}
            {summary.asayu_trip_count != null
              ? ` · 対象 ${summary.asayu_trip_count}回`
              : ""}
            。次の表示は翌月20日以降の更新後です。
          </p>
        </article>
      ) : (
        <article className="card">
          <p className="sum">
            まだ還元サマリがありません。毎月19〜26日（付与は翌月20日）に
            smile-etc で確認し、Jarvis が更新します。
          </p>
        </article>
      )}

      <section className="etc-guide" aria-label="申請・還元の案内">
        <h2>伊勢湾岸・平日朝夕の申請方法</h2>
        <p className="sum">
          <strong>伊勢湾岸だけ別申請する制度はありません。</strong>
          平日朝夕割引の還元を受けるには{" "}
          <strong>ETCマイレージサービスへの登録</strong>
          が必要です（登録済みなら追加手続き不要）。
        </p>
        <ul className="etc-guide-list">
          <li>
            マイレージ登録・残高確認:{" "}
            <a
              href="https://www.smile-etc.jp/"
              target="_blank"
              rel="noreferrer"
            >
              smile-etc.jp
            </a>
          </li>
          <li>
            平日朝夕の条件・還元率:{" "}
            <a
              href="https://dc2.c-nexco.co.jp/etc/discount/etc/weekday"
              target="_blank"
              rel="noreferrer"
            >
              NEXCO中日本 平日朝夕割引
            </a>
          </li>
          <li>
            還元の確認: smile-etc ログイン →「還元額明細」（利用月の翌月20日以降）
          </li>
          <li>
            対象時間: 平日 6–9時 / 17–20時に入口または出口。朝・夕それぞれ月内1回目まで
          </li>
          <li>
            還元率: 対象5〜9回≈30%／10回以上≈50%（地方部・最大100km相当）
          </li>
        </ul>
        <p className="meta">
          先輩への共有用: 「伊勢湾岸の通勤還元はマイレージ登録が申請。専用フォームはない。
          付与は利用月の翌月20日」で十分です。
        </p>
      </section>

      <section>
        <h2>過去の還元</h2>
        {history.length === 0 && !hasRebate ? (
          <p className="empty">履歴はまだありません</p>
        ) : (
          <ul className="etc-history-list">
            {(history.length
              ? history
              : [
                  {
                    target_month: summary.target_month,
                    rebate_yen: summary.rebate_yen,
                    asayu_trip_count: summary.asayu_trip_count,
                    asayu_rate_pct: summary.asayu_rate_pct,
                    savings_yen: summary.savings_yen,
                    at: summary.at,
                    note: summary.note,
                  },
                ]
            ).map((h, i) => (
              <li key={`${h.target_month || "x"}-${i}`}>
                <strong>{h.target_month || "—"}</strong>
                {" · "}
                {fmtYen(h.rebate_yen)}
                {h.asayu_trip_count != null
                  ? ` · ${h.asayu_trip_count}回`
                  : " · 回数—"}
                {h.asayu_rate_pct != null ? ` · ${fmtRate(h.asayu_rate_pct)}` : ""}
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
