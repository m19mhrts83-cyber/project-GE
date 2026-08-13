import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import { corporateCycle, personalCycle } from "@/lib/taxCycle";

export const dynamic = "force-dynamic";

type CaseRow = {
  id: string;
  fiscal_year: number;
  title: string;
  status: string;
  scope: string;
  csv_path: string | null;
};

type EvidenceRow = {
  id: string;
  fiscal_year: number;
  scope: string | null;
  doc_kind: string;
  subject: string | null;
  original_filename: string | null;
  stored_path: string;
  received_at: string | null;
};

function ingested(
  scope: "personal" | "corporate",
  year: number,
  cases: CaseRow[],
  evidence: EvidenceRow[]
): boolean {
  const ev = evidence.filter(
    (e) => e.fiscal_year === year && (e.scope || "personal") === scope
  );
  if (ev.length > 0) return true;
  if (scope === "personal") {
    return cases.some(
      (c) =>
        c.scope === "personal" &&
        c.fiscal_year === year &&
        (c.status === "csv_ready" || c.status === "registered" || c.status === "closed")
    );
  }
  return false;
}

export default async function TaxPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const personal = personalCycle();
  const corporate = corporateCycle();

  const [{ data: cases }, { data: evidence }, { data: jobs }] = await Promise.all([
    supabase
      .from("kurashift_tax_cases")
      .select("id, fiscal_year, title, status, scope, csv_path")
      .order("fiscal_year", { ascending: false }),
    supabase
      .from("kurashift_tax_evidence")
      .select(
        "id, fiscal_year, scope, doc_kind, subject, original_filename, stored_path, received_at"
      )
      .order("created_at", { ascending: false })
      .limit(60),
    supabase
      .from("kurashift_jobs")
      .select("id, job_type, status, title, created_at, error_text")
      .like("job_type", "tax_%")
      .order("created_at", { ascending: false })
      .limit(8),
  ]);

  const caseRows = (cases ?? []) as CaseRow[];
  const evRows = (evidence ?? []) as EvidenceRow[];
  const personalIn = ingested("personal", personal.year, caseRows, evRows);
  const corporateIn = ingested("corporate", corporate.year, caseRows, evRows);

  return (
    <Shell active="/tax" email={user?.email ?? null}>
      <p className="page-kicker">② · 申告サイクル</p>
      <h1>申告</h1>
      <p className="sub">
        いま回す年は日付で切り替わります。個人は12月締め・2月申告、法人は5月決算・8月頃。
        未取込で窓に入ったら「そろそろ取り込みます」。Jarvis に下の文で依頼してください。
      </p>

      <div className="grid">
        <article className="card">
          <header>
            <span className="lvl">個人</span>
            <strong>{personal.label}</strong>
          </header>
          <p>
            <span className={`status-pill ${personalIn ? "ingested" : "pending"}`}>
              {personalIn ? "取り込んでいる" : "取り込んでいない"}
            </span>
          </p>
          <p className="meta">{personal.windowLabel}</p>
          {personal.window && !personalIn ? (
            <div className="card notice" style={{ marginTop: 12, marginBottom: 12 }}>
              <strong>そろそろ取り込みます</strong>
              <p className="meta" style={{ marginTop: 6 }}>
                Jarvis へ: 「{personal.jarvisPrompt}」
              </p>
            </div>
          ) : (
            <p className="meta" style={{ marginTop: 8 }}>
              依頼文: 「{personal.jarvisPrompt}」
            </p>
          )}
          <EnqueueJobButton
            jobType="tax_build_yayoi_csv"
            title={`弥生CSV ${personal.year}`}
            payload={{ fiscal_year: personal.year, scope: "personal" }}
            label="弥生CSVを作る"
          />
          <EnqueueJobButton
            jobType="tax_ingest_accountant_mail"
            title={`税理士メール取込 ${personal.year}`}
            payload={{ fiscal_year: personal.year, scope: "personal", limit: 30 }}
            label="税理士メールを取り込む"
          />
        </article>

        <article className="card">
          <header>
            <span className="lvl">法人</span>
            <strong>{corporate.label}</strong>
          </header>
          <p>
            <span className={`status-pill ${corporateIn ? "ingested" : "pending"}`}>
              {corporateIn ? "取り込んでいる" : "取り込んでいない"}
            </span>
          </p>
          <p className="meta">
            {corporate.windowLabel}。Knees bee 大野さんの決算PDF（年1回）
          </p>
          {corporate.window && !corporateIn ? (
            <div className="card notice" style={{ marginTop: 12, marginBottom: 12 }}>
              <strong>そろそろ取り込みます</strong>
              <p className="meta" style={{ marginTop: 6 }}>
                Jarvis へ: 「{corporate.jarvisPrompt}」
              </p>
            </div>
          ) : (
            <p className="meta" style={{ marginTop: 8 }}>
              依頼文: 「{corporate.jarvisPrompt}」
            </p>
          )}
          <EnqueueJobButton
            jobType="tax_ingest_accountant_mail"
            title={`法人メール取込 ${corporate.year}`}
            payload={{ fiscal_year: corporate.year, scope: "corporate", limit: 20 }}
            label="大野さんメールを取り込む"
          />
        </article>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">案件</span>
          <strong>履歴</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>区分</th>
              <th>年度</th>
              <th>タイトル</th>
              <th>状態</th>
            </tr>
          </thead>
          <tbody>
            {caseRows.length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  まだ案件がありません
                </td>
              </tr>
            ) : (
              caseRows.map((c) => (
                <tr key={c.id}>
                  <td>{c.scope === "corporate" ? "法人" : "個人"}</td>
                  <td>{c.fiscal_year}</td>
                  <td>{c.title}</td>
                  <td>{c.status}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">証憑</span>
          <strong>メール添付など</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>区分</th>
              <th>年度</th>
              <th>件名／ファイル</th>
              <th>再出力</th>
            </tr>
          </thead>
          <tbody>
            {evRows.length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  証憑はまだありません
                </td>
              </tr>
            ) : (
              evRows.map((e) => (
                <tr key={e.id}>
                  <td>{e.scope === "corporate" ? "法人" : "個人"}</td>
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
