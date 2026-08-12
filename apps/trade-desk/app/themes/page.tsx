import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import NewThemeForm from "@/components/NewThemeForm";
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
    .limit(40);

  return (
    <Shell active="/themes" email={user?.email ?? null}>
      <h1>テーマ運用</h1>
      <p className="sub">
        提案→相談→承認→実行→振り返り。資産ステータスから草案を自動生成するか、手動で追加。
      </p>

      <EnqueueJobButton
        jobType="theme_propose_from_status"
        title="資産ステータスから提案を生成"
        payload={{ limit: 6 }}
        label="ステータスから提案を生成"
      />

      <NewThemeForm />

      <div className="card">
        <header>
          <span className="lvl">Theme</span>
          <strong>カード一覧</strong>
        </header>
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
                  まだテーマがありません。上の生成ボタンか手動フォームから追加してください。
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
                  <td>
                    {t.amount_jpy != null ? fmtYen(Number(t.amount_jpy)) : "—"}
                  </td>
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
