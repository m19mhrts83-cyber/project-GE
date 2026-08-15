import Shell from "@/components/Shell";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import { buildBRate4Rows, fmtPct } from "@/lib/bRate4";
import {
  RE_PROPERTY_MASTER,
  getRePropertyMaster,
  loansForProperty,
} from "@/lib/rePropertyMaster";
import { dscrLabel, fmtDscr, simpleDscr } from "@/lib/reDscr";
import {
  ROI_ASSETS,
  unitBreakdown,
  type PropertyUnitRow,
} from "@/lib/roiAssets";

export const dynamic = "force-dynamic";

type Unit = {
  id: string;
  property_id: string;
  property_name: string;
  room: string;
  status: string;
  rent: number | null;
  note: string | null;
  updated_at: string;
  payload: Record<string, unknown> | null;
};

type LoanRow = {
  id: string;
  name: string | null;
  lender: string | null;
  category_major: string | null;
  balance_jpy: number | string | null;
  monthly_payment_jpy: number | string | null;
  annual_payment_jpy: number | string | null;
  rate_pct: number | string | null;
  tags: string[] | null;
  payload: Record<string, unknown> | null;
  synced_at: string | null;
};

export default async function RealEstatePropertiesPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: units } = await supabase
    .from("property_units")
    .select(
      "id, property_id, property_name, room, status, rent, note, updated_at, payload"
    )
    .order("property_name", { ascending: true })
    .order("room", { ascending: true });

  const { data: loans } = await supabase
    .from("kurashift_loan_tracker_loans")
    .select(
      "id, name, lender, category_major, balance_jpy, monthly_payment_jpy, annual_payment_jpy, rate_pct, tags, payload, synced_at"
    )
    .order("balance_jpy", { ascending: false, nullsFirst: false })
    .limit(80);

  const loanRows = (loans || []) as LoanRow[];
  const bRate4 = buildBRate4Rows(loanRows);
  const loanPayMonth = loanRows.reduce((s, l) => {
    const v = l.monthly_payment_jpy == null ? 0 : Number(l.monthly_payment_jpy);
    return s + (Number.isFinite(v) ? v : 0);
  }, 0);

  const byProp = new Map<
    string,
    { name: string; units: Unit[]; rentSum: number; vacant: number }
  >();
  for (const u of (units || []) as Unit[]) {
    const key = u.property_id || u.property_name;
    let g = byProp.get(key);
    if (!g) {
      g = { name: u.property_name, units: [], rentSum: 0, vacant: 0 };
      byProp.set(key, g);
    }
    g.units.push(u);
    const broken = unitBreakdown(u as PropertyUnitRow);
    g.rentSum += broken.totalRent ?? (Number(u.rent) || 0);
    if (u.status === "vacant") g.vacant += 1;
  }

  const orderedIds = [
    ...RE_PROPERTY_MASTER.map((p) => p.id),
    ...[...byProp.keys()].filter(
      (id) => !RE_PROPERTY_MASTER.some((p) => p.id === id)
    ),
  ];

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="c" />
      <p className="page-kicker">③-C · 保有物件</p>
      <h1>物件マスタ</h1>
      <p className="sub">
        <code>property_units</code> の号室現況。ローン残高は{" "}
        <a
          href="https://loan-tracker-plum.vercel.app/"
          target="_blank"
          rel="noreferrer"
        >
          借入残高トラッカー
        </a>
        が正本（ここでは二重入力しない）。
        {" · "}
        買い物評価（利回り・返済比率）は <a href="/roi">ROI</a>
        {" · "}
        運用進捗は <a href="/realestate">③-A</a>
      </p>

      <div className="card notice">
        <header>
          <span className="lvl">3C-PREP</span>
          <strong>物件 × 名義 × ローン（最小揃え）</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          正本: <code>config/kurashift_re_property_master.yaml</code>
          {" · "}
          管理・住所: <code>config/property_info.yaml</code>
        </p>
        <p className="meta" style={{ marginTop: 8 }}>
          レントロール合計と月返済を並べ、家賃−返済の関係が一目で分かるようにしています。
        </p>
        <p className="meta" style={{ marginTop: 6 }}>
          DSCR 簡易 = 月家賃合計 ÷ 月返済合計（業界定番。厳密 NOI
          ではない）。目安 1.2×以上。
        </p>
        <table>
          <thead>
            <tr>
              <th>物件</th>
              <th>名義</th>
              <th className="num">号室</th>
              <th className="num">レントロール合計</th>
              <th className="num">月返済合計</th>
              <th className="num">家賃−返済</th>
              <th className="num">DSCR</th>
              <th>紐づくローン</th>
            </tr>
          </thead>
          <tbody>
            {RE_PROPERTY_MASTER.map((p) => {
              const live = byProp.get(p.id);
              const linked = loansForProperty(p.id, loanRows);
              const rentSum = live?.rentSum ?? 0;
              const paySum = linked.reduce((s, l) => {
                const v =
                  l.monthly_payment_jpy == null
                    ? 0
                    : Number(l.monthly_payment_jpy);
                return s + (Number.isFinite(v) ? v : 0);
              }, 0);
              const gap = live ? rentSum - paySum : null;
              const dscr = live ? simpleDscr(rentSum, paySum) : null;
              return (
                <tr key={p.id}>
                  <td>
                    {p.name}
                    <div className="meta">{p.id}</div>
                  </td>
                  <td className="meta">
                    {p.owner}
                    {p.ownerEntity ? `（${p.ownerEntity}）` : ""}
                  </td>
                  <td className="num meta">
                    {live ? live.units.length : "—"}/{p.roomsExpected}
                  </td>
                  <td className="num">
                    {live ? (
                      <strong>{fmtYen(rentSum)}／月</strong>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="num meta">
                    {linked.length ? `${fmtYen(paySum)}／月` : "—"}
                  </td>
                  <td className="num">
                    {gap == null ? (
                      "—"
                    ) : (
                      <strong>
                        {gap >= 0 ? "+" : ""}
                        {fmtYen(gap)}
                      </strong>
                    )}
                  </td>
                  <td className="num">
                    <strong>{fmtDscr(dscr)}</strong>
                    <div className="meta">{dscrLabel(dscr)}</div>
                  </td>
                  <td className="meta">
                    {linked.length
                      ? linked.map((l) => l.name || l.id).join(" / ")
                      : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card">
        <header>
          <span className="lvl">B-RATE-4</span>
          <strong>正味（表面利回り − 金利）</strong>
        </header>
        {loanRows.length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            ローン投影後に表示されます。
          </p>
        ) : (
          <>
            <p className="meta" style={{ marginTop: 8 }}>
              ローン正本の月返済合計（参考）: {fmtYen(loanPayMonth)}／月 ·{" "}
              <a href="/realestate">不動産ハブの一覧 →</a>
            </p>
            <p className="meta" style={{ marginTop: 4 }}>
              合算 = 残高加重平均。キャラメルは本担保＋諸費用を合算。式は Discover §B-RATE-4。
            </p>
            <table>
              <thead>
                <tr>
                  <th>物件</th>
                  <th className="num">レントロール</th>
                  <th className="num">月返済</th>
                  <th className="num">家賃−返済</th>
                  <th className="num">DSCR</th>
                  <th className="num">表面</th>
                  <th className="num">合算金利</th>
                  <th className="num">正味</th>
                </tr>
              </thead>
              <tbody>
                {bRate4.map((r) => {
                  const live = byProp.get(r.propertyId);
                  const rentSum = live?.rentSum ?? null;
                  const pay = r.monthlyPaymentJpy;
                  const gap =
                    rentSum != null && pay != null ? rentSum - pay : null;
                  const dscr = simpleDscr(rentSum, pay);
                  return (
                    <tr key={r.propertyId}>
                      <td>{r.name}</td>
                      <td className="num">
                        {rentSum != null ? (
                          <strong>{fmtYen(rentSum)}／月</strong>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="num meta">
                        {pay != null ? `${fmtYen(pay)}／月` : "—"}
                      </td>
                      <td className="num">
                        {gap == null ? (
                          "—"
                        ) : (
                          <strong>
                            {gap >= 0 ? "+" : ""}
                            {fmtYen(gap)}
                          </strong>
                        )}
                      </td>
                      <td className="num">
                        <strong>{fmtDscr(dscr)}</strong>
                      </td>
                      <td className="num meta">{fmtPct(r.surfaceYieldPct)}</td>
                      <td className="num meta">{fmtPct(r.loanRatePct)}</td>
                      <td className="num">
                        <strong>{fmtPct(r.netSpreadPct)}</strong>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="card">
        <header>
          <span className="lvl">③-C</span>
          <strong>ローン投影（loan-tracker）</strong>
        </header>
        {loanRows.length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            まだ投影がありません。JSON:{" "}
            <code>240_融資/loan_tracker_export/loans.json</code> →{" "}
            <code>jarvis_kurashift_loan_tracker_sync.py --apply</code>。Discover:{" "}
            <code>docs/KURASHIFT_loan_tracker_Discover.md</code>
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>大分類</th>
                <th>名称</th>
                <th>金融機関</th>
                <th>残高</th>
                <th>月返済</th>
                <th>金利</th>
              </tr>
            </thead>
            <tbody>
              {loanRows.map((l) => (
                <tr key={l.id}>
                  <td className="meta">{l.category_major || "—"}</td>
                  <td>{l.name}</td>
                  <td className="meta">{l.lender || "—"}</td>
                  <td className="meta">
                    {l.balance_jpy != null ? fmtYen(Number(l.balance_jpy)) : "—"}
                  </td>
                  <td className="meta">
                    {l.monthly_payment_jpy != null
                      ? fmtYen(Number(l.monthly_payment_jpy))
                      : "—"}
                  </td>
                  <td className="meta">
                    {l.rate_pct != null ? `${Number(l.rate_pct)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {orderedIds.map((pid) => {
        const g = byProp.get(pid);
        const master = getRePropertyMaster(pid);
        const linked = loansForProperty(pid, loanRows);
        if (!g && !master) return null;
        const title = master?.name || g?.name || pid;
        const roomCount = g?.units.length ?? 0;
        const vacant = g?.vacant ?? 0;
        const rentSum = g?.rentSum ?? 0;
        const roi = ROI_ASSETS.find((a) => a.unitPropertyId === pid);
        const paySum = linked.reduce((s, l) => {
          const v =
            l.monthly_payment_jpy == null ? 0 : Number(l.monthly_payment_jpy);
          return s + (Number.isFinite(v) ? v : 0);
        }, 0);
        const gap = g ? rentSum - paySum : null;
        return (
          <div className="card" key={pid}>
            <header>
              <span className="lvl">{pid}</span>
              <strong>{title}</strong>
            </header>
            <p className="meta" style={{ marginTop: 6 }}>
              {master
                ? `${master.owner}（${master.ownerEntity}）· 取得 ${master.acquired} · ${master.address}`
                : null}
            </p>
            <p className="meta" style={{ marginTop: 4 }}>
              {g
                ? `${roomCount} 室 · 空室 ${vacant}`
                : "号室データなし"}
              {master?.managers?.length
                ? ` · 管理 ${master.managers.join(" / ")}`
                : ""}
              {" · "}
              <a href="/roi">ROI（評価）→</a>
            </p>
            {roi?.fullRentBuyNote ? (
              <p className="meta" style={{ marginTop: 4 }}>
                年収メモ: {roi.fullRentBuyNote}
              </p>
            ) : null}
            <table style={{ marginTop: 10 }}>
              <thead>
                <tr>
                  <th className="num">レントロール合計</th>
                  <th className="num">月返済合計</th>
                  <th className="num">家賃−返済</th>
                  <th className="num">DSCR</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="num">
                    {g ? <strong>{fmtYen(rentSum)}／月</strong> : "—"}
                  </td>
                  <td className="num meta">
                    {linked.length ? `${fmtYen(paySum)}／月` : "—"}
                  </td>
                  <td className="num">
                    {gap == null ? (
                      "—"
                    ) : (
                      <strong>
                        {gap >= 0 ? "+" : ""}
                        {fmtYen(gap)}／月
                      </strong>
                    )}
                  </td>
                  <td className="num">
                    <strong>{fmtDscr(simpleDscr(rentSum, paySum))}</strong>
                    <div className="meta">
                      {dscrLabel(simpleDscr(rentSum, paySum))}
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            {linked.length > 0 ? (
              <table style={{ marginTop: 10 }}>
                <thead>
                  <tr>
                    <th>紐づくローン</th>
                    <th>金融機関</th>
                    <th className="num">残高</th>
                    <th className="num">月返済</th>
                    <th className="num">金利</th>
                  </tr>
                </thead>
                <tbody>
                  {linked.map((l) => (
                    <tr key={l.id}>
                      <td>{l.name}</td>
                      <td className="meta">{l.lender || "—"}</td>
                      <td className="num meta">
                        {l.balance_jpy != null
                          ? fmtYen(Number(l.balance_jpy))
                          : "—"}
                      </td>
                      <td className="num meta">
                        {l.monthly_payment_jpy != null
                          ? fmtYen(Number(l.monthly_payment_jpy))
                          : "—"}
                      </td>
                      <td className="num meta">
                        {l.rate_pct != null ? `${Number(l.rate_pct)}%` : "—"}
                      </td>
                    </tr>
                  ))}
                  <tr>
                    <td colSpan={3}>
                      <strong>月返済合計</strong>
                      <span className="meta">（対レントロール {g ? fmtYen(rentSum) : "—"}）</span>
                    </td>
                    <td className="num">
                      <strong>{fmtYen(paySum)}</strong>
                    </td>
                    <td />
                  </tr>
                </tbody>
              </table>
            ) : (
              <p className="meta" style={{ marginTop: 8 }}>
                紐づくローンなし
              </p>
            )}
            {g ? (
              <table style={{ marginTop: 10 }}>
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
                  {g.units.map((u) => {
                    const b = unitBreakdown(u as PropertyUnitRow);
                    return (
                      <tr key={u.id}>
                        <td>{u.room}</td>
                        <td>{u.status === "vacant" ? "空室" : "入居"}</td>
                        <td className="num meta">
                          {b.rent != null ? fmtYen(b.rent) : "—"}
                        </td>
                        <td className="num meta">
                          {b.mgmt != null ? fmtYen(b.mgmt) : "—"}
                        </td>
                        <td className="num">
                          {b.totalRent != null ? fmtYen(b.totalRent) : "—"}
                        </td>
                        <td className="meta">{u.note || "—"}</td>
                      </tr>
                    );
                  })}
                  <tr>
                    <td colSpan={4}>
                      <strong>レントロール合計</strong>
                      <span className="meta">
                        （対月返済 {linked.length ? fmtYen(paySum) : "—"}
                        {roi
                          ? ` · 評価用満室年収 ${roi.fullRentBuy != null ? `${Math.round(roi.fullRentBuy / 10_000)}万` : "—"}`
                          : ""}
                        ）
                      </span>
                    </td>
                    <td className="num">
                      <strong>{fmtYen(rentSum)}／月</strong>
                    </td>
                    <td className="meta">
                      {gap == null
                        ? ""
                        : `家賃−返済 ${gap >= 0 ? "+" : ""}${fmtYen(gap)}`}
                    </td>
                  </tr>
                </tbody>
              </table>
            ) : null}
          </div>
        );
      })}

      {(units || []).length === 0 ? (
        <div className="card">
          <p className="meta">号室データがありません。</p>
        </div>
      ) : null}
    </Shell>
  );
}
