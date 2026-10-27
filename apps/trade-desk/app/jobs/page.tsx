import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { readMacWatchStatus } from "@/lib/macWatchStatus";

export const dynamic = "force-dynamic";

const STATUS_JA: Record<string, { label: string; pill: string }> = {
  queued: { label: "待ち", pill: "pending" },
  running: { label: "実行中", pill: "pending" },
  succeeded: { label: "完了", pill: "owned" },
  done: { label: "完了", pill: "owned" },
  failed: { label: "失敗", pill: "failed" },
};

function firstLine(text: string, max = 80): string {
  const line = text.split("\n").find((l) => l.trim()) ?? text;
  return line.length > max ? `${line.slice(0, max)}…` : line;
}

export default async function JobsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [{ data: jobs }, watch] = await Promise.all([
    supabase
      .from("kurashift_jobs")
      .select(
        "id, job_type, status, title, created_at, started_at, finished_at, error_text, log_text, artifacts"
      )
      .order("created_at", { ascending: false })
      .limit(50),
    readMacWatchStatus(120),
  ]);

  return (
    <Shell active="/jobs" email={user?.email ?? null}>
      <h1>ジョブ</h1>
      <p className="sub">
        画面のボタンで予約した処理の一覧です。Mac が起きていれば数秒〜数十秒で実行され、スリープ中は次に起動したときに実行されます。
        「失敗」の行だけ確認すれば十分です。ログは各行の「詳細」を開くと見られます。
      </p>
      <p className="meta" style={{ marginBottom: 12 }}>
        {watch.label}
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
                  <td>
                    <span
                      className={`status-pill ${STATUS_JA[j.status]?.pill ?? ""}`}
                      title={j.status}
                    >
                      {STATUS_JA[j.status]?.label ?? j.status}
                    </span>
                  </td>
                  <td>{j.job_type}</td>
                  <td>
                    {j.title}
                    {j.log_text ? (
                      <details style={{ marginTop: 4 }}>
                        <summary className="meta">詳細（ログ）</summary>
                        <pre
                          className="meta"
                          style={{
                            maxHeight: 160,
                            overflow: "auto",
                            whiteSpace: "pre-wrap",
                            marginTop: 6,
                          }}
                        >
                          {j.log_text.slice(-800)}
                        </pre>
                      </details>
                    ) : null}
                  </td>
                  <td className="meta" style={{ whiteSpace: "nowrap" }}>
                    {j.created_at?.slice(0, 16).replace("T", " ")}
                  </td>
                  <td className="meta">
                    {j.error_text ? (
                      <details>
                        <summary>{firstLine(j.error_text)}</summary>
                        <pre style={{ whiteSpace: "pre-wrap", margin: "6px 0 0" }}>
                          {j.error_text}
                        </pre>
                      </details>
                    ) : (
                      "—"
                    )}
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
