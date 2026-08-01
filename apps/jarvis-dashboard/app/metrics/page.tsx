import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

function fmt(n: number | null | undefined) {
  if (n == null) return "—";
  return `${Math.round(n).toLocaleString("ja-JP")}円`;
}

function fmtNum(n: number | null | undefined, unit = "") {
  if (n == null) return "—";
  const s = Number.isInteger(n)
    ? Math.round(n).toLocaleString("ja-JP")
    : n.toLocaleString("ja-JP", { maximumFractionDigits: 2 });
  return unit ? `${s}${unit}` : s;
}

export default async function MetricsPage() {
  const supabase = await createClient();
  const { data: rows } = await supabase
    .from("metrics")
    .select("*")
    .in("metric", [
      "cashflow",
      "rent_income",
      "expense_total",
      "repair_expense",
      "income_total",
      "vpoint_balance",
      "etc_rebate_last",
      "energy_buy_yen",
      "energy_buy_kwh",
      "energy_buy_unit",
      "energy_sell_yen",
      "energy_sell_kwh",
      "energy_sell_unit",
      "energy_solar_loan_yen",
      "energy_net_cf",
    ])
    .order("recorded_at", { ascending: false })
    .limit(800);

  // latest month per entity+metric
  const latest = new Map<string, number>();
  const months = new Set<string>();
  for (const r of rows || []) {
    const ym = String(r.recorded_at).slice(0, 7);
    months.add(ym);
    const key = `${ym}|${r.entity}|${r.metric}`;
    if (!latest.has(key)) latest.set(key, Number(r.value));
  }
  const ymList = [...months].sort().reverse().slice(0, 6);
  const cur = ymList[0];

  const pick = (ent: string, metric: string, ym = cur) =>
    ym ? latest.get(`${ym}|${ent}|${metric}`) : undefined;

  const energyMonths = [
    ...new Set(
      (rows || [])
        .filter((r) => String(r.metric).startsWith("energy_"))
        .map((r) => String(r.recorded_at).slice(0, 7)),
    ),
  ]
    .sort()
    .reverse()
    .slice(0, 36);

  const { data: meta } = await supabase.from("sync_meta").select("key,value");
  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));

  const softLatest = (metric: string) => {
    const hit = (rows || []).find((r) => r.metric === metric);
    return hit ? Number(hit.value) : undefined;
  };
  const vpt = softLatest("vpoint_balance");
  const etc = softLatest("etc_rebate_last");

  return (
    <Shell active="/metrics">
      <h1>モチベーション数値</h1>
      <p className="sub">
        Zaim CSV から法人／個人別に集計。部屋単位の修繕引き当てはせず法人単位で見ます。
      </p>
      <div className="stats">
        <div className="stat">
          対象月 <strong>{cur || "—"}</strong>
        </div>
        <div className="stat">
          法人 手残り <strong>{fmt(pick("corporate", "cashflow"))}</strong>
        </div>
        <div className="stat">
          個人 手残り <strong>{fmt(pick("personal", "cashflow"))}</strong>
        </div>
        <div className="stat">
          Vポイント <strong>{vpt != null ? `${Math.round(vpt).toLocaleString("ja-JP")}pt` : "—"}</strong>
        </div>
        <div className="stat">
          ETC還元（直近） <strong>{fmt(etc)}</strong>
        </div>
        <div className="stat">
          finance sync {metaMap.finance_pushed_at ?? "未"}
        </div>
      </div>

      <h2>{cur || "—"} の内訳</h2>
      <article className="card">
        <header>
          <strong>法人</strong>
        </header>
        <p className="sum">家賃収入 {fmt(pick("corporate", "rent_income"))}</p>
        <p className="sum">支出合計 {fmt(pick("corporate", "expense_total"))}</p>
        <p className="sum">修繕 {fmt(pick("corporate", "repair_expense"))}</p>
        <p className="sum">手残り（CF） {fmt(pick("corporate", "cashflow"))}</p>
      </article>
      <article className="card">
        <header>
          <strong>個人</strong>
        </header>
        <p className="sum">家賃収入 {fmt(pick("personal", "rent_income"))}</p>
        <p className="sum">支出合計 {fmt(pick("personal", "expense_total"))}</p>
        <p className="sum">手残り（CF） {fmt(pick("personal", "cashflow"))}</p>
      </article>

      <h2>電力・太陽光キャッシュフロー（自宅）</h2>
      <p className="sub">
        買電=エネワン（サイサン）／売電=中部電力PG／ローン=オリコ。energy sync{" "}
        {metaMap.energy_cf_pushed_at ?? "未"}。消費kWhはポータルワン連携後に埋まります（売電kWhはFIT推定あり）。
      </p>
      {!energyMonths.length ? (
        <p className="empty">energy metrics 未 push（jarvis_energy_cf_collect.py --push）</p>
      ) : (
        energyMonths.map((ym) => (
          <article key={`e-${ym}`} className="card">
            <header>
              <strong>{ym}</strong>
            </header>
            <p className="sum">
              買電 {fmt(pick("home", "energy_buy_yen", ym))}
              {pick("home", "energy_buy_kwh", ym) != null
                ? `（${fmtNum(pick("home", "energy_buy_kwh", ym), "kWh")}）`
                : ""}
              {" · "}
              単価 {fmtNum(pick("home", "energy_buy_unit", ym), "円/kWh")}
            </p>
            <p className="sum">
              売電 {fmt(pick("home", "energy_sell_yen", ym))}
              {pick("home", "energy_sell_kwh", ym) != null
                ? `（${fmtNum(pick("home", "energy_sell_kwh", ym), "kWh")}）`
                : ""}
              {" · "}
              単価 {fmtNum(pick("home", "energy_sell_unit", ym), "円/kWh")}
            </p>
            <p className="meta">
              ローン {fmt(pick("home", "energy_solar_loan_yen", ym))} ／ ネット CF{" "}
              {fmt(pick("home", "energy_net_cf", ym))}
            </p>
          </article>
        ))
      )}

      <h2>月次トレンド（手残り）</h2>
      {!ymList.length ? (
        <p className="empty">metrics 未 push</p>
      ) : (
        ymList.map((ym) => (
          <article key={ym} className="card">
            <header>
              <strong>{ym}</strong>
            </header>
            <p className="sum">
              法人 {fmt(pick("corporate", "cashflow", ym))} ／ 個人{" "}
              {fmt(pick("personal", "cashflow", ym))}
            </p>
            <p className="meta">
              家賃 法人 {fmt(pick("corporate", "rent_income", ym))} ／ 個人{" "}
              {fmt(pick("personal", "rent_income", ym))}
            </p>
          </article>
        ))
      )}
    </Shell>
  );
}
