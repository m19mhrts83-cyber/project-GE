import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { fmtPct, fmtYen } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function PaperPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [{ data: risk }, { data: positions }, { data: signals }] =
    await Promise.all([
      supabase.from("trade_risk_state").select("*").eq("id", "paper").maybeSingle(),
      supabase
        .from("trade_positions")
        .select("symbol, qty, avg_price, opened_at, status")
        .eq("mode", "paper")
        .eq("status", "open")
        .order("opened_at", { ascending: false }),
      supabase
        .from("trade_signals")
        .select("signal_date, symbol, side, score, reason, status")
        .order("signal_date", { ascending: false })
        .limit(20),
    ]);

  return (
    <Shell active="/paper" email={user?.email ?? null}>
      <h1>ペーパー</h1>
      <p className="sub">
        実発注なし。平均回帰＋分割建てのリズム。ライブは承認ゲート後。
      </p>
      <div className="grid">
        <article className="card">
          <header>
            <span className="lvl">リスク</span>
            <strong>
              {risk?.kill_switch ? (
                <span className="bad">kill</span>
              ) : (
                `tranche ${risk?.tranche ?? 1}`
              )}
            </strong>
          </header>
          <p>資本 {fmtYen(risk?.capital_jpy)}</p>
          <p className="meta">
            現在 {fmtYen(risk?.current_equity)} / ピーク{" "}
            {fmtYen(risk?.peak_equity)} / DD {fmtPct(risk?.drawdown_pct)}
          </p>
          {risk?.kill_reason ? (
            <p className="warn">{risk.kill_reason}</p>
          ) : null}
        </article>
      </div>

      <h2 style={{ marginTop: 28, fontSize: "1.05rem" }}>建玉</h2>
      <div className="card">
        {(positions ?? []).length === 0 ? (
          <p className="meta">オープン建玉なし</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>銘柄</th>
                <th>数量</th>
                <th>平均</th>
                <th>開始</th>
              </tr>
            </thead>
            <tbody>
              {(positions ?? []).map((p) => (
                <tr key={`${p.symbol}-${p.opened_at}`}>
                  <td>{p.symbol}</td>
                  <td>{p.qty}</td>
                  <td>{fmtYen(p.avg_price)}</td>
                  <td>{p.opened_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2 style={{ marginTop: 28, fontSize: "1.05rem" }}>直近シグナル</h2>
      <div className="card">
        {(signals ?? []).length === 0 ? (
          <p className="meta">まだありません</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>日</th>
                <th>銘柄</th>
                <th>側</th>
                <th>score</th>
                <th>理由</th>
              </tr>
            </thead>
            <tbody>
              {(signals ?? []).map((s, i) => (
                <tr key={`${s.signal_date}-${s.symbol}-${i}`}>
                  <td>{s.signal_date}</td>
                  <td>{s.symbol}</td>
                  <td>{s.side}</td>
                  <td>{s.score ?? "—"}</td>
                  <td className="meta">{s.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Shell>
  );
}
