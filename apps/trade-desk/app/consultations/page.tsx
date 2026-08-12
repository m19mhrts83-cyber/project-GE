import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function ConsultationsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: rows } = await supabase
    .from("kurashift_consultations")
    .select(
      "id, title, body, lane, decision, status, created_at, updated_at"
    )
    .order("created_at", { ascending: false })
    .limit(50);

  return (
    <Shell active="/consultations" email={user?.email ?? null}>
      <h1>相談記録</h1>
      <p className="sub">
        ローカル Jarvis での相談・判断をアプリで閲覧。登録例:{" "}
        <code>jarvis_kurashift_consult.py --title … --body …</code>
      </p>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>状態</th>
              <th>レーン</th>
              <th>タイトル</th>
              <th>判断</th>
              <th>日時</th>
            </tr>
          </thead>
          <tbody>
            {(rows ?? []).length === 0 ? (
              <tr>
                <td colSpan={5} className="meta">
                  まだ相談記録がありません
                </td>
              </tr>
            ) : (
              (rows ?? []).map((r) => (
                <tr key={r.id}>
                  <td>{r.status}</td>
                  <td>{r.lane}</td>
                  <td>
                    <strong>{r.title}</strong>
                    <div className="meta" style={{ whiteSpace: "pre-wrap" }}>
                      {r.body.slice(0, 280)}
                      {r.body.length > 280 ? "…" : ""}
                    </div>
                  </td>
                  <td className="meta">{r.decision ?? "—"}</td>
                  <td className="meta">{r.created_at?.slice(0, 19)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
