import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function ThemesPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: themes } = await supabase
    .from("kurashift_themes")
    .select(
      "id, title, hypothesis, amount_jpy, duration_note, funding_path, status, review_note, created_at"
    )
    .order("created_at", { ascending: false })
    .limit(30);

  return (
    <Shell active="/themes" email={user?.email ?? null}>
      <h1>テーマ運用</h1>
      <p className="sub">
        提案→相談→承認→実行→振り返り。まずは一般的で実行しやすい提案から。定石は相談で改善。
      </p>

      <div className="card">
        <header>
          <span className="lvl">Theme</span>
          <strong>カード一覧</strong>
        </header>
        <p className="meta">
          新規テーマは Jarvis 相談後に登録。プレビュージョブは実弾を出しません。
        </p>
        <table>
          <thead>
            <tr>
              <th>状態</th>
              <th>タイトル</th>
              <th>金額</th>
              <th>経路</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(themes ?? []).length === 0 ? (
              <tr>
                <td colSpan={5} className="meta">
                  まだテーマがありません。Jarvis で相談した内容を登録してください。
                </td>
              </tr>
            ) : (
              (themes ?? []).map((t) => (
                <tr key={t.id}>
                  <td>{t.status}</td>
                  <td>
                    <strong>{t.title}</strong>
                    <div className="meta">{t.hypothesis}</div>
                  </td>
                  <td>{t.amount_jpy != null ? fmtYen(Number(t.amount_jpy)) : "—"}</td>
                  <td className="meta">{t.funding_path ?? "—"}</td>
                  <td>
                    <EnqueueJobButton
                      jobType="theme_preview"
                      title={`preview ${t.title}`}
                      payload={{ theme_id: t.id }}
                      label="プレビュー"
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
