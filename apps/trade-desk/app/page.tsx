import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { fmtPct, fmtYen } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [{ data: snaps }, { data: risk }, { data: signals }, { data: positions }] =
    await Promise.all([
      supabase
        .from("portfolio_snapshots")
        .select("account_id, as_of, value_jpy, source")
        .order("as_of", { ascending: false })
        .limit(40),
      supabase.from("trade_risk_state").select("*").eq("id", "paper").maybeSingle(),
      supabase
        .from("trade_signals")
        .select("id")
        .eq("status", "paper")
        .gte(
          "signal_date",
          new Date(Date.now() - 14 * 86400000).toISOString().slice(0, 10)
        ),
      supabase
        .from("trade_positions")
        .select("id")
        .eq("mode", "paper")
        .eq("status", "open"),
    ]);

  const latestByAccount = new Map<
    string,
    { as_of: string; value_jpy: number; source: string | null }
  >();
  for (const row of snaps ?? []) {
    if (!latestByAccount.has(row.account_id)) {
      latestByAccount.set(row.account_id, {
        as_of: row.as_of,
        value_jpy: Number(row.value_jpy),
        source: row.source,
      });
    }
  }
  const total = [...latestByAccount.values()].reduce(
    (s, r) => s + r.value_jpy,
    0
  );

  return (
    <Shell active="/" email={user?.email ?? null}>
      <h1>概要</h1>
      <p className="sub">
        ダッシュボードとは別アプリ。注文はまだ出さない（立花 KYC 待ち）。
      </p>

      <div className="grid">
        <article className="card">
          <header>
            <span className="lvl">KYC</span>
            <strong>立花証券e支店</strong>
          </header>
          <p>申込番号 2026081200001（2026-08-12 受付）</p>
          <p className="meta">
            次: 届いた口座開設資料に記入し、本人確認＋マイナンバーを返送。API
            鍵は口座開設後。
          </p>
        </article>
        <article className="card">
          <header>
            <span className="lvl">資産スナップ</span>
            <strong>{fmtYen(total)}</strong>
          </header>
          <p className="meta">{latestByAccount.size}口座の最新値合計</p>
        </article>
        <article className="card">
          <header>
            <span className="lvl">ペーパー</span>
            <strong>
              {risk?.kill_switch ? (
                <span className="bad">停止中</span>
              ) : (
                `T${risk?.tranche ?? 1}`
              )}
            </strong>
          </header>
          <p className="meta">
            資本 {fmtYen(risk?.capital_jpy)} / DD {fmtPct(risk?.drawdown_pct)}
          </p>
          <p className="meta">
            直近14日シグナル {signals?.length ?? 0} / 建玉{" "}
            {positions?.length ?? 0}
          </p>
        </article>
        <article className="card">
          <header>
            <span className="lvl">ロールアウト</span>
            <strong>A シミュレーション</strong>
          </header>
          <p className="warn">
            直近1年バックテストは DD 27%。ペーパー確信・実弾はまだ進めない。
          </p>
        </article>
      </div>
    </Shell>
  );
}
