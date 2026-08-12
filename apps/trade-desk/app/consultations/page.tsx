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

  const ids = (rows ?? []).map((r) => r.id);
  const themeByConsult = new Map<
    string,
    { id: string; title: string; status: string }
  >();
  if (ids.length > 0) {
    const { data: themes } = await supabase
      .from("kurashift_themes")
      .select("id, title, status, consultation_id")
      .in("consultation_id", ids);
    for (const t of themes ?? []) {
      if (t.consultation_id) {
        themeByConsult.set(t.consultation_id, {
          id: t.id,
          title: t.title,
          status: t.status,
        });
      }
    }
  }

  return (
    <Shell active="/consultations" email={user?.email ?? null}>
      <h1>相談記録</h1>
      <p className="sub">
        テーマを「相談中」にするとここにメモが付きます。行を開いて内容を確認し、そこから承認できます。
      </p>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>状態</th>
              <th>レーン</th>
              <th>タイトル</th>
              <th>テーマ</th>
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
              (rows ?? []).map((r) => {
                const th = themeByConsult.get(r.id);
                return (
                  <tr key={r.id}>
                    <td>{r.status}</td>
                    <td>{r.lane}</td>
                    <td>
                      <a href={`/consultations/${r.id}`}>
                        <strong>{r.title}</strong>
                      </a>
                      <div className="meta" style={{ whiteSpace: "pre-wrap" }}>
                        {r.body.slice(0, 160)}
                        {r.body.length > 160 ? "…" : ""}
                      </div>
                      {r.decision ? (
                        <div className="meta">判断: {r.decision}</div>
                      ) : null}
                      {th?.status === "consulting" ? (
                        <div style={{ marginTop: 6 }}>
                          <a
                            className="btn primary"
                            href={`/consultations/${r.id}`}
                            style={{ fontSize: 12, padding: "4px 8px" }}
                          >
                            内容確認→承認
                          </a>
                        </div>
                      ) : null}
                    </td>
                    <td className="meta">
                      {th ? (
                        <a href={`/themes/${th.id}`}>
                          {th.title}
                          <br />
                          <span>({th.status})</span>
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="meta">{r.created_at?.slice(0, 19)}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
