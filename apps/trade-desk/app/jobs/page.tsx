import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function JobsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: jobs } = await supabase
    .from("kurashift_jobs")
    .select(
      "id, job_type, status, title, created_at, started_at, finished_at, error_text, log_text, artifacts"
    )
    .order("created_at", { ascending: false })
    .limit(50);

  return (
    <Shell active="/jobs" email={user?.email ?? null}>
      <h1>ジョブ</h1>
      <p className="sub">
        アプリのボタン → queued →{" "}
        <code>jarvis_kurashift_job_worker.py</code>（Mac）が実行。
      </p>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>状態</th>
              <th>種別</th>
              <th>タイトル</th>
              <th>作成</th>
              <th>エラー</th>
            </tr>
          </thead>
          <tbody>
            {(jobs ?? []).length === 0 ? (
              <tr>
                <td colSpan={5} className="meta">
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
                    {j.log_text ? (
                      <pre
                        className="meta"
                        style={{
                          maxHeight: 120,
                          overflow: "auto",
                          whiteSpace: "pre-wrap",
                          marginTop: 6,
                        }}
                      >
                        {j.log_text.slice(-800)}
                      </pre>
                    ) : null}
                  </td>
                  <td className="meta">{j.created_at?.slice(0, 19)}</td>
                  <td className="meta">{j.error_text ?? "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
