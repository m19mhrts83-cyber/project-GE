import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function PortfolioPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: accounts } = await supabase
    .from("portfolio_accounts")
    .select("id, name, kind, institution, ingest")
    .eq("active", true)
    .order("id");
  const { data: snaps } = await supabase
    .from("portfolio_snapshots")
    .select("account_id, as_of, value_jpy, source")
    .order("as_of", { ascending: false })
    .limit(80);

  const latest = new Map<
    string,
    { as_of: string; value_jpy: number; source: string | null }
  >();
  for (const row of snaps ?? []) {
    if (!latest.has(row.account_id)) {
      latest.set(row.account_id, {
        as_of: row.as_of,
        value_jpy: Number(row.value_jpy),
        source: row.source,
      });
    }
  }

  return (
    <Shell active="/portfolio" email={user?.email ?? null}>
      <h1>資産</h1>
      <p className="sub">週次スクレイプ／Zaim から入れたスナップショット。</p>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>口座</th>
              <th>種別</th>
              <th>評価</th>
              <th>日付</th>
              <th>ソース</th>
            </tr>
          </thead>
          <tbody>
            {(accounts ?? []).map((a) => {
              const s = latest.get(a.id);
              return (
                <tr key={a.id}>
                  <td>
                    {a.name}
                    <div className="meta">{a.institution}</div>
                  </td>
                  <td>{a.kind}</td>
                  <td>{s ? fmtYen(s.value_jpy) : "—"}</td>
                  <td>{s?.as_of ?? "—"}</td>
                  <td>{s?.source ?? a.ingest}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
