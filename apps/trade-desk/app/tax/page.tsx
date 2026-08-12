import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function TaxPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const year = new Date().getFullYear() - 1;

  const [{ data: cases }, { data: evidence }, { data: jobs }] = await Promise.all([
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
    supabase
      .from("kurashift_jobs")
      .select("id, job_type, status, title, created_at, error_text")
      .like("job_type", "tax_%")
      .order("created_at", { ascending: false })
      .limit(8),
  ]);

  return (
    <Shell active="/tax" email={user?.email ?? null}>
      <h1>個人申告</h1>
      <p className="sub">
        個人のみ（弥生CSV）。法人は税理士委託。サイクル: CSV作成 → 証憑取込 →
        一覧確認 →（承認後に）弥生登録。
      </p>

      <div className="card">
        <header>
          <span className="lvl">サイクル D</span>
          <strong>{year}年分を回す</strong>
        </header>
        <ol className="meta" style={{ marginTop: 8, paddingLeft: 18 }}>
          <li>弥生CSVを作る（Zaimサマリー→勘定ドラフト。本登録はしない）</li>
          <li>税理士メールを取り込む（admin Gmail）</li>
          <li>
            メール0件なら OneDrive{" "}
            <code>…/kurashift/{year}/evidence/inbox/</code>{" "}
            にPDFを置き、手動取込
          </li>
          <li>下の一覧でパスと件名を確認。必要なら証憑出力</li>
        </ol>
        <EnqueueJobButton
          jobType="tax_build_yayoi_csv"
          title={`弥生CSV ${year}`}
          payload={{ fiscal_year: year }}
          label="1. 弥生CSVを作る"
        />
        <EnqueueJobButton
          jobType="tax_ingest_accountant_mail"
          title={`税理士メール取込 ${year}`}
          payload={{ fiscal_year: year, limit: 30 }}
          label="2. 税理士メールを取り込む"
        />
        <EnqueueJobButton
          jobType="tax_ingest_manual_dir"
          title={`証憑手動取込 ${year}`}
          payload={{ fiscal_year: year }}
          label="3. 手動フォルダ（inbox）を取り込む"
        />
        <p className="meta" style={{ marginTop: 8 }}>
          CSVは<strong>ドラフト</strong>（勘定マップ未整備の費目はスキップされうる）。弥生本登録UIはありません。
        </p>
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
                  案件なし — 上の「弥生CSVを作る」から
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
                  証憑はまだありません — 「税理士メールを取り込む」後に増えます
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

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">最近のジョブ</span>
          <strong>tax_*</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>状態</th>
              <th>種別</th>
              <th>タイトル</th>
              <th>作成</th>
            </tr>
          </thead>
          <tbody>
            {(jobs ?? []).length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  ジョブなし
                </td>
              </tr>
            ) : (
              (jobs ?? []).map((j) => (
                <tr key={j.id}>
                  <td>{j.status}</td>
                  <td>{j.job_type}</td>
                  <td>
                    {j.title}
                    {j.error_text ? (
                      <div className="meta">{j.error_text}</div>
                    ) : null}
                  </td>
                  <td className="meta">{j.created_at?.slice(0, 19)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
