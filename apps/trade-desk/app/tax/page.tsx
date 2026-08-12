import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function TaxPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [{ data: cases }, { data: evidence }] = await Promise.all([
    supabase
      .from("kurashift_tax_cases")
      .select("id, fiscal_year, title, status, csv_path, notes, updated_at")
      .eq("scope", "personal")
      .order("fiscal_year", { ascending: false }),
    supabase
      .from("kurashift_tax_evidence")
      .select(
        "id, fiscal_year, doc_kind, subject, original_filename, stored_path, received_at"
      )
      .order("created_at", { ascending: false })
      .limit(40),
  ]);

  return (
    <Shell active="/tax" email={user?.email ?? null}>
      <h1>個人申告</h1>
      <p className="sub">
        個人のみ（弥生CSV）。法人は税理士委託。メール添付は証憑として保管・再出力。
      </p>

      <div className="card">
        <header>
          <span className="lvl">アクション</span>
          <strong>弥生CSV / メール取込</strong>
        </header>
        <EnqueueJobButton
          jobType="tax_build_yayoi_csv"
          title="弥生CSVを作る"
          payload={{ fiscal_year: 2025 }}
        />
        <EnqueueJobButton
          jobType="tax_ingest_accountant_mail"
          title="税理士メールを取り込む"
          payload={{ fiscal_year: 2025 }}
        />
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">案件</span>
          <strong>個人</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>年度</th>
              <th>タイトル</th>
              <th>状態</th>
              <th>CSV</th>
            </tr>
          </thead>
          <tbody>
            {(cases ?? []).length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  案件なし
                </td>
              </tr>
            ) : (
              (cases ?? []).map((c) => (
                <tr key={c.id}>
                  <td>{c.fiscal_year}</td>
                  <td>{c.title}</td>
                  <td>{c.status}</td>
                  <td className="meta">{c.csv_path ?? "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">証憑</span>
          <strong>税理士添付など</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>年度</th>
              <th>件名／ファイル</th>
              <th>再出力</th>
            </tr>
          </thead>
          <tbody>
            {(evidence ?? []).length === 0 ? (
              <tr>
                <td colSpan={3} className="meta">
                  証憑はまだありません
                </td>
              </tr>
            ) : (
              (evidence ?? []).map((e) => (
                <tr key={e.id}>
                  <td>{e.fiscal_year}</td>
                  <td>
                    {e.subject || e.original_filename || e.doc_kind}
                    <div className="meta">{e.stored_path}</div>
                  </td>
                  <td>
                    <EnqueueJobButton
                      jobType="tax_export_evidence"
                      title={`export ${e.id}`}
                      payload={{ fiscal_year: e.fiscal_year, evidence_id: e.id }}
                      label="証憑出力"
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
