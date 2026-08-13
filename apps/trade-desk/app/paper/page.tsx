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
      <div className="card notice" style={{ marginBottom: 16 }}>
        <header>
          <span className="lvl">Lab · ゲート</span>
          <strong>立花 API・少額実弾</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          本線外。口座・鍵が揃うまで<strong>実弾は撃たない</strong>。紙トレードと
          ROI の立花行は閲覧のみ。解錠はユーザー明示＋別タスク。
        </p>
        <ul className="meta" style={{ marginTop: 6 }}>
          <li>API 鍵パスは `.env.jarvis_private` のみ（チャットに出さない）</li>
          <li>少額実弾は kill_switch OFF かつ別ジョブ承認後</li>
          <li>健美家フィード等の外部物件クローラは Phase C 対象外のまま</li>
        </ul>
      </div>
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
