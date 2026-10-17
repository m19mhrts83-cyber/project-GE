import Link from "next/link";
import Shell from "@/components/Shell";
import YenRateChart, { type YenPoint } from "@/components/YenRateChart";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "yen_rate";

type CompareRow = {
  label?: string;
  ref_date?: string;
  ref?: number | null;
  change?: number | null;
  change_pct?: number | null;
  missing?: boolean;
};

type LastStats = {
  last?: number | null;
  last_date?: string | null;
  high?: number | null;
  high_date?: string | null;
  low?: number | null;
  low_date?: string | null;
  change?: number | null;
  change_pct?: number | null;
};

function fmtPx(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(2)}`;
}

function fmtSigned(n: number | null | undefined, suffix = "") {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}${suffix}`;
}

export default async function YenPage() {
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

  const last = (
    payload.last && typeof payload.last === "object"
      ? (payload.last as LastStats)
      : {}
  ) as LastStats;

  const compares = Array.isArray(payload.compares)
    ? (payload.compares as CompareRow[])
    : [];

  const evaluation =
    typeof payload.evaluation === "string" ? payload.evaluation : "";
  const news = typeof payload.news === "string" ? payload.news : "";
  const source =
    typeof payload.source === "string"
      ? payload.source
      : watch?.source || "—";

  const since = new Date();
  since.setDate(since.getDate() - 90);
  const sinceStr = since.toISOString().slice(0, 10);

  const { data: series } = await supabase
    .from("yen_rate_daily")
    .select("trade_date, close")
    .eq("symbol", "USDJPY")
    .gte("trade_date", sinceStr)
    .order("trade_date", { ascending: true });

  const points: YenPoint[] = (series || []).map((r) => ({
    trade_date: String(r.trade_date),
    close: Number(r.close),
  }));

  const checkedAt = watch?.checked_at
    ? String(watch.checked_at).replace("T", " ").slice(0, 19)
    : "—";

  return (
    <Shell active="/yen">
      <h1>円動向（USD/JPY）</h1>
      <p className="sub">
        615 円動向報告係の投影。報告・見立てのみで、売買・ポジション指図はしない。
      </p>

      <article className="card level-info">
        <header>
          <span className="lvl">終値</span>
          <strong>
            {fmtPx(last.last)} 円
            {last.last_date ? `（${last.last_date}）` : ""}
          </strong>
        </header>
        <p className="meta">
          ソース: {source} · 最終投影: {checkedAt} · 社員:{" "}
          <Link href="/agent-team">615</Link>
        </p>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: 12,
            marginTop: 12,
          }}
        >
          <div>
            <span className="meta">前日比</span>
            <strong style={{ display: "block" }}>
              {fmtSigned(last.change)}（{fmtSigned(last.change_pct, "%")}）
            </strong>
          </div>
          <div>
            <span className="meta">期間高値</span>
            <strong style={{ display: "block" }}>
              {fmtPx(last.high)}
              {last.high_date ? (
                <span className="meta"> {last.high_date}</span>
              ) : null}
            </strong>
          </div>
          <div>
            <span className="meta">期間安値</span>
            <strong style={{ display: "block" }}>
              {fmtPx(last.low)}
              {last.low_date ? (
                <span className="meta"> {last.low_date}</span>
              ) : null}
            </strong>
          </div>
        </div>
      </article>

      <article className="card">
        <header>
          <strong>直近〜90日</strong>
        </header>
        {points.length >= 2 ? (
          <YenRateChart points={points} />
        ) : (
          <p className="empty">
            まだ日次レートがありません。Mac で{" "}
            <code>jarvis_yen_rate_watch.py --apply --with-news</code>{" "}
            を実行するとここに載ります。
          </p>
        )}
      </article>

      {compares.length > 0 ? (
        <article className="card">
          <header>
            <strong>比較</strong>
          </header>
          <table className="vpoint-rate-table">
            <thead>
              <tr>
                <th>比較</th>
                <th>参照日</th>
                <th>当時</th>
                <th>差分</th>
                <th>変化率</th>
              </tr>
            </thead>
            <tbody>
              {compares.map((c) => (
                <tr key={c.label || "?"}>
                  <td>{c.label}</td>
                  {c.missing ? (
                    <>
                      <td>—</td>
                      <td>—</td>
                      <td>—</td>
                      <td>—</td>
                    </>
                  ) : (
                    <>
                      <td>{c.ref_date}</td>
                      <td>{fmtPx(c.ref ?? null)}</td>
                      <td>{fmtSigned(c.change)}</td>
                      <td>{fmtSigned(c.change_pct, "%")}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </article>
      ) : null}

      {evaluation ? (
        <article className="card">
          <header>
            <strong>見立て（売買指図なし）</strong>
          </header>
          <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{evaluation}</p>
          {news ? (
            <p className="meta" style={{ marginTop: 8 }}>
              ニュース材料: {news}
            </p>
          ) : null}
        </article>
      ) : null}

      <p className="meta">
        状況ウォッチ:{" "}
        <Link href={`/situation?watch=${WATCH_ID}#watch-${WATCH_ID}`}>
          yen_rate
        </Link>
        {" · "}
        KURASHIFT の資産画面とは分離（ここは円の動き報告）
      </p>
    </Shell>
  );
}
