import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { DASHBOARD_URL, fmtMan, fmtPct, fmtYen } from "@/lib/format";
import {
  ROI_ASSETS,
  acquireTotal,
  allInYield,
  cashOnCash,
  cfRoi,
  costOnBodyPct,
  fullCf,
  groupUnitsLive,
  occRate,
  payYear,
  surfaceYield,
  type PropertyUnitRow,
} from "@/lib/roiAssets";

export const dynamic = "force-dynamic";

const FIN_CORE = [
  "sony_life",
  "sony_life_chikage",
  "prudential_life",
  "prudential_life_chikage",
  "axa_life",
  "akatsuki_bond",
  "sbi_index",
  "bloomo",
  "mhi_stock",
  "tachibana_trade",
] as const;

const FIN_LOANS = [
  "sony_life_policy_loan",
  "sony_life_chikage_policy_loan",
  "prudential_life_policy_loan",
  "prudential_life_chikage_policy_loan",
] as const;

type SnapRow = {
  account_id: string;
  as_of: string;
  value_jpy: number | string | null;
  cost_jpy: number | string | null;
};

type FlowRow = {
  account_id: string;
  kind: string;
  amount_jpy: number | string | null;
};

function num(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

export default async function RoiPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: unitRows } = await supabase
    .from("property_units")
    .select("property_id, property_name, room, status, rent, note, payload")
    .order("property_id")
    .order("room");
  const liveMap = groupUnitsLive((unitRows || []) as PropertyUnitRow[]);

  const { data: accounts } = await supabase
    .from("portfolio_accounts")
    .select("id, name, kind")
    .eq("active", true);
  const nameById = new Map((accounts ?? []).map((a) => [a.id, a.name]));

  const { data: snaps } = await supabase
    .from("portfolio_snapshots")
    .select("account_id, as_of, value_jpy, cost_jpy")
    .order("as_of", { ascending: false })
    .limit(200);

  const latest = new Map<string, SnapRow>();
  const prev = new Map<string, SnapRow>();
  for (const row of (snaps ?? []) as SnapRow[]) {
    if (!latest.has(row.account_id)) {
      latest.set(row.account_id, row);
      continue;
    }
    const cur = latest.get(row.account_id);
    if (cur && row.as_of !== cur.as_of && !prev.has(row.account_id)) {
      prev.set(row.account_id, row);
    }
  }

  const { data: flows } = await supabase
    .from("portfolio_cashflows")
    .select("account_id, kind, amount_jpy");
  const flowByAccount = new Map<string, { inJpy: number; outJpy: number }>();
  for (const f of (flows ?? []) as FlowRow[]) {
    const amt = num(f.amount_jpy) ?? 0;
    const cur = flowByAccount.get(f.account_id) ?? { inJpy: 0, outJpy: 0 };
    if (f.kind === "in" || f.kind === "buy" || f.kind === "premium") {
      cur.outJpy += Math.abs(amt);
    } else if (f.kind === "out" || f.kind === "sell" || f.kind === "dividend") {
      cur.inJpy += Math.abs(amt);
    }
    flowByAccount.set(f.account_id, cur);
  }

  const iLive = liveMap.get("grandole-i");
  const snapAsOf = [...latest.values()][0]?.as_of ?? null;

  return (
    <Shell active="/roi" email={user?.email ?? null}>
      <div className="roi-page">
        <p className="page-kicker">② · 買い物ごとの振り返り</p>
        <h1>ROI（物件・金融）</h1>
        <p className="sub">
          1行＝1回の購入。Zaim の 19収入−19支出の合計ではありません。
          年収の現況は Jarvis ダッシュボードの号室（
          <a href={`${DASHBOARD_URL}/properties`} target="_blank" rel="noreferrer">
            /properties
          </a>
          ）を読み、レントロールと突き合わせます。
        </p>

        <div className="card notice">
          <header>
            <span className="lvl">定義</span>
            <strong>この画面の ROI は年次です</strong>
          </header>
          <p className="meta" style={{ marginTop: 8 }}>
            「マンスリー ROI」という別計算はありません。月の列は年額÷12
            の見やすさ用です。
          </p>
          <ul className="def-list meta">
            <li>
              <strong>表面利回り</strong> = 満室年収 ÷ 本体購入価格（経費を含まない）
            </li>
            <li>
              <strong>取得利回り</strong> = 満室年収 ÷（本体＋購入経費）
            </li>
            <li>
              <strong>CF-ROI</strong>（Numbers 流）=（満室年収 − 年返済）÷
              年返済。運営経費は引かない。買い時の比較用
            </li>
            <li>
              <strong>CoC</strong>（キャッシュオンキャッシュ）= 満室CF ÷
              自己資金。収支評価
            </li>
            <li>
              <strong>金融の単純ROI</strong> =（いまの評価 −
              取得原価）÷ 取得原価。原価が無い口座は「—」
            </li>
          </ul>
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <header>
            <span className="lvl">不動産</span>
            <strong>購入時評価 ＋ 現況</strong>
          </header>
          <p className="meta">
            本体と経費を分けて、本体に対する上乗せ率を見ます。志賀本通I
            の決済支払合計は 65,214,215円（6,521万）で確定。
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>状態</th>
                  <th>物件</th>
                  <th>取得</th>
                  <th className="num">本体</th>
                  <th className="num">購入経費</th>
                  <th className="num">合計</th>
                  <th className="num">経費率</th>
                  <th className="num">決済支払</th>
                  <th className="num">満室年収</th>
                  <th className="num">表面</th>
                  <th className="num">取得利回り</th>
                  <th className="num">年返済</th>
                  <th className="num">満室CF</th>
                  <th className="num">CF-ROI</th>
                  <th className="num">CoC</th>
                  <th className="num">入居率いま</th>
                </tr>
              </thead>
              <tbody>
                {ROI_ASSETS.map((a) => {
                  const live = a.unitPropertyId
                    ? liveMap.get(a.unitPropertyId)
                    : undefined;
                  const liveAnnual =
                    live && live.totalRentMonth > 0
                      ? live.totalRentMonth * 12
                      : null;
                  const fullRent =
                    a.fullRentBuy ?? liveAnnual ?? null;
                  const total = acquireTotal(a);
                  const annualPay = payYear(a.monthlyPayBuy);
                  const cf = fullCf(fullRent, annualPay);
                  const nowRate = occRate(live);
                  return (
                    <tr
                      key={a.id}
                      className={a.status === "sold" ? "sold" : undefined}
                    >
                      <td>
                        <span className={`status-pill ${a.status}`}>
                          {a.status === "owned" ? "保有" : "売却済み"}
                        </span>
                      </td>
                      <td>
                        {a.name}
                        <div className="meta">{a.owner}</div>
                      </td>
                      <td className="meta">{a.bought}</td>
                      <td className="num">{fmtMan(a.bodyPrice)}</td>
                      <td className="num">
                        {fmtMan(a.acquireCost)}
                        {!a.acquireCostComplete && a.acquireCost != null ? (
                          <div className="meta">判明分</div>
                        ) : null}
                      </td>
                      <td className="num">{fmtMan(total)}</td>
                      <td className="num">{fmtPct(costOnBodyPct(a))}</td>
                      <td className="num">
                        {a.settlementPay != null ? fmtMan(a.settlementPay) : "—"}
                      </td>
                      <td className="num">
                        {fmtMan(fullRent)}
                        {a.fullRentBuy == null && liveAnnual != null ? (
                          <div className="meta">現況仮</div>
                        ) : null}
                      </td>
                      <td className="num">
                        {fmtPct(surfaceYield(fullRent, a.bodyPrice))}
                      </td>
                      <td className="num">
                        {fmtPct(allInYield(fullRent, total))}
                      </td>
                      <td className="num">{fmtMan(annualPay)}</td>
                      <td className="num">{fmtMan(cf)}</td>
                      <td className="num">{fmtPct(cfRoi(fullRent, annualPay))}</td>
                      <td className="num">{fmtPct(cashOnCash(cf, a.equity))}</td>
                      <td className="num">
                        {a.status === "sold"
                          ? "—"
                          : nowRate != null && live
                            ? `${fmtPct(nowRate, 0)}（${live.occupied}/${live.total}）`
                            : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="meta" style={{ marginTop: 10 }}>
            経費率 = 購入経費 ÷ 本体。決済支払は当日現金（志賀本通I
            は手付済みのため本体全額ではない）。
          </p>
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <header>
            <span className="lvl">入居率</span>
            <strong>購入時 → 2025 → いま</strong>
          </header>
          <table>
            <thead>
              <tr>
                <th>物件</th>
                <th>購入時</th>
                <th>2025</th>
                <th>いま</th>
                <th>メモ</th>
              </tr>
            </thead>
            <tbody>
              {ROI_ASSETS.filter((a) => a.status === "owned").map((a) => {
                const live = a.unitPropertyId
                  ? liveMap.get(a.unitPropertyId)
                  : undefined;
                const now =
                  live && live.total
                    ? `${fmtPct(live.occupied / live.total, 0)}（${live.occupied}/${live.total}）`
                    : "—";
                return (
                  <tr key={a.id}>
                    <td>{a.name}</td>
                    <td>{a.occBuy ?? "—"}</td>
                    <td>{a.occ2025 ?? "—"}</td>
                    <td>{now}</td>
                    <td className="meta">{a.actualNote}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <header>
            <span className="lvl">I</span>
            <strong>志賀本通I 年収 — ダッシュボード号室</strong>
          </header>
          <p className="meta">
            レントロール共有後にこの表と突き合わせます。いまは Jarvis
            ダッシュボードの号室賃料＋管理費を仮の満室年収にしています。
          </p>
          {!iLive ? (
            <p className="meta">号室データがありません。</p>
          ) : (
            <>
              <p style={{ margin: "8px 0 12px" }}>
                入居 {iLive.occupied}/{iLive.total}
                {" · "}家賃月 {fmtYen(iLive.rentMonth)}
                {" · "}家賃＋管理費月 {fmtYen(iLive.totalRentMonth)}
                {" → 年 "}
                <strong>{fmtYen(iLive.totalRentMonth * 12)}</strong>
                （{fmtMan(iLive.totalRentMonth * 12)}）
              </p>
              <table>
                <thead>
                  <tr>
                    <th>号室</th>
                    <th>状態</th>
                    <th className="num">家賃</th>
                    <th className="num">管理費</th>
                    <th className="num">合計</th>
                    <th>メモ</th>
                  </tr>
                </thead>
                <tbody>
                  {iLive.units.map((u) => (
                    <tr key={u.room}>
                      <td>{u.room}</td>
                      <td>{u.status === "occupied" ? "入居" : u.status}</td>
                      <td className="num">{fmtYen(u.rent)}</td>
                      <td className="num">{fmtYen(u.mgmt)}</td>
                      <td className="num">{fmtYen(u.totalRent)}</td>
                      <td className="meta">{u.note ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>

        <div className="grid" style={{ marginTop: 16 }}>
          {ROI_ASSETS.filter((a) => a.status === "owned").map((a) => {
            const live = a.unitPropertyId
              ? liveMap.get(a.unitPropertyId)
              : undefined;
            const liveAnnual =
              live && live.totalRentMonth > 0
                ? live.totalRentMonth * 12
                : null;
            const fullNow = liveAnnual ?? a.fullRentBuy;
            const payNow = payYear(a.monthlyPayNow ?? a.monthlyPayBuy);
            return (
              <article className="card" key={`${a.id}-note`}>
                <header>
                  <span className="lvl">{a.owner}</span>
                  <strong>{a.name}</strong>
                </header>
                <p className="meta">{a.fullRentBuyNote}</p>
                <p className="meta">{a.acquireCostNote}</p>
                {a.monthlyPayNow != null &&
                a.monthlyPayBuy != null &&
                a.monthlyPayNow !== a.monthlyPayBuy ? (
                  <p className="meta">
                    いまの返済での満室 CF-ROI{" "}
                    {fmtPct(cfRoi(fullNow, payNow))}
                    （年返済 {fmtMan(payNow)}）
                  </p>
                ) : null}
                {a.settlementPay != null ? (
                  <p className="meta">
                    自己資金 {fmtYen(a.equity)} / 決済支払{" "}
                    {fmtYen(a.settlementPay)}
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <header>
            <span className="lvl">売却済み</span>
            <strong>幸田さんワンルーム3戸</strong>
          </header>
          <p className="meta">
            一覧から外さず履歴として残しています。金額は Numbers
            「ROI・リバランスまとめ」。経費内訳は未分割です。
          </p>
          <ul className="meta" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {ROI_ASSETS.filter((a) => a.status === "sold").map((a) => (
              <li key={a.id}>
                {a.name} … {a.soldNote}
              </li>
            ))}
          </ul>
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <header>
            <span className="lvl">金融</span>
            <strong>一般的な ROI の並び</strong>
          </header>
          <p className="meta">
            都度購入して評価する前提。単純ROI は取得原価が必要です。週次スナップ
            {snapAsOf ? `（${snapAsOf}）` : ""}
            の評価と、1本前スナップとの差を収支の代わりに並べます。払込累計が無い口座は
            ROI を出しません。
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>口座</th>
                  <th className="num">評価</th>
                  <th className="num">取得原価</th>
                  <th className="num">含み損益</th>
                  <th className="num">単純ROI</th>
                  <th className="num">入出金累計</th>
                  <th className="num">評価の差</th>
                </tr>
              </thead>
              <tbody>
                {FIN_CORE.map((id) => {
                  const s = latest.get(id);
                  const p = prev.get(id);
                  const value = num(s?.value_jpy);
                  const cost = num(s?.cost_jpy);
                  const gain =
                    value != null && cost != null ? value - cost : null;
                  const simple =
                    value != null && cost != null && cost !== 0
                      ? (value - cost) / cost
                      : null;
                  const fl = flowByAccount.get(id);
                  const flowNet = fl ? fl.inJpy - fl.outJpy : null;
                  const delta =
                    value != null && p
                      ? value - (num(p.value_jpy) ?? 0)
                      : null;
                  return (
                    <tr key={id}>
                      <td>{nameById.get(id) || id}</td>
                      <td className="num">{fmtYen(value)}</td>
                      <td className="num">{fmtYen(cost)}</td>
                      <td className="num">{fmtYen(gain)}</td>
                      <td className="num">{fmtPct(simple)}</td>
                      <td className="num">
                        {flowNet == null ? "未登録" : fmtYen(flowNet)}
                      </td>
                      <td className="num">{fmtYen(delta)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="meta" style={{ marginTop: 10 }}>
            評価の差は直前スナップとの比較（ROI ではない）。契約者貸付は下表。
          </p>
          <table style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>控除</th>
                <th className="num">残高</th>
              </tr>
            </thead>
            <tbody>
              {FIN_LOANS.filter(
                (id) => (num(latest.get(id)?.value_jpy) ?? 0) !== 0
              ).length === 0 ? (
                <tr>
                  <td colSpan={2} className="meta">
                    契約者貸付の残高はありません
                  </td>
                </tr>
              ) : (
                FIN_LOANS.map((id) => {
                  const value = num(latest.get(id)?.value_jpy) ?? 0;
                  if (value === 0) return null;
                  return (
                    <tr key={id}>
                      <td>{nameById.get(id) || id}</td>
                      <td className="num">−{fmtYen(value)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}
