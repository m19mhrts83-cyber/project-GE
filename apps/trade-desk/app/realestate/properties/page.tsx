import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";

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
};

export default async function RealEstatePropertiesPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: units } = await supabase
    .from("property_units")
    .select(
      "id, property_id, property_name, room, status, rent, note, updated_at"
    )
    .order("property_name", { ascending: true })
    .order("room", { ascending: true });

  const { data: loans } = await supabase
    .from("kurashift_loan_tracker_loans")
    .select(
      "id, name, lender, category_major, balance_jpy, monthly_payment_jpy, annual_payment_jpy, rate_pct, synced_at"
    )
    .order("balance_jpy", { ascending: false, nullsFirst: false })
    .limit(80);

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
    g.rentSum += Number(u.rent) || 0;
    if (u.status === "vacant") g.vacant += 1;
  }

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
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
        <a href="/realestate">不動産ハブ →</a>
      </p>

      <div className="card notice">
        <header>
          <span className="lvl">範囲</span>
          <strong>Phase 1（一覧）</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          号室は一覧のみ。ローンは借入残高トラッカーの読取投影（下表）。空室メモは
          note をそのまま表示します。
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">③-C</span>
          <strong>ローン投影（loan-tracker）</strong>
        </header>
        {(loans || []).length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            まだ投影がありません。データはトラッカー画面ではなく、estate の Google Drive
            （アプリ専用ファイル）にあります。Discover:{" "}
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
              {(loans || []).map((l) => (
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

      {[...byProp.entries()].map(([pid, g]) => (
        <div className="card" key={pid}>
          <header>
            <span className="lvl">{pid}</span>
            <strong>{g.name}</strong>
          </header>
          <p className="meta" style={{ marginTop: 6 }}>
            {g.units.length} 室 · 空室 {g.vacant} · 家賃合計{" "}
            {fmtYen(g.rentSum)}／月
          </p>
          <table>
            <thead>
              <tr>
                <th>号室</th>
                <th>状態</th>
                <th>家賃</th>
                <th>メモ</th>
              </tr>
            </thead>
            <tbody>
              {g.units.map((u) => (
                <tr key={u.id}>
                  <td>{u.room}</td>
                  <td>{u.status === "vacant" ? "空室" : "入居"}</td>
                  <td className="meta">
                    {u.rent != null ? fmtYen(u.rent) : "—"}
                  </td>
                  <td className="meta">{u.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {(units || []).length === 0 ? (
        <div className="card">
          <p className="meta">号室データがありません。</p>
        </div>
      ) : null}
    </Shell>
  );
}
