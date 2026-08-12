import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import NewThemeForm from "@/components/NewThemeForm";
import ThemeStatusActions from "@/components/ThemeStatusActions";
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
      "id, title, hypothesis, amount_jpy, duration_note, funding_path, status, review_note, consultation_id, created_at"
    )
    .order("created_at", { ascending: false })
    .limit(40);

  return (
    <Shell active="/themes" email={user?.email ?? null}>
      <h1>テーマ運用</h1>
      <p className="sub">
        draft → <strong>相談中（内容確認）</strong> → 承認 → 実行。相談を挟むときは確認画面から承認。草案から直接承認も可。承認前に実弾は動きません。
      </p>

      <EnqueueJobButton
        jobType="theme_propose_from_status"
        title="資産ステータスから提案を生成"
        payload={{ limit: 6 }}
        label="ステータスから提案を生成"
      />
      <EnqueueJobButton
        jobType="theme_propose_from_status"
        title="年1リバランス提案を含めて生成"
        payload={{ limit: 8, include_index_rb: true }}
        label="年1RB込みで再生成"
      />
      <EnqueueJobButton
        jobType="theme_ensure_index_rb"
        title="インデックス年1RBカードを確保"
        payload={{}}
        label="年1RBカードを確保"
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
              <th>経路／操作</th>
            </tr>
          </thead>
          <tbody>
            {(themes ?? []).length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  まだテーマがありません。
                </td>
              </tr>
            ) : (
              (themes ?? []).map((t) => (
                <tr key={t.id}>
                  <td>
                    <strong>{t.status}</strong>
                  </td>
                  <td>
                    <a href={`/themes/${t.id}`}>
                      <strong>{t.title}</strong>
                    </a>
                    <div className="meta">{t.hypothesis}</div>
                    {t.duration_note ? (
                      <div className="meta">期間: {t.duration_note}</div>
                    ) : null}
                  </td>
                  <td>
                    {t.amount_jpy != null ? fmtYen(Number(t.amount_jpy)) : "—"}
                  </td>
                  <td>
                    <div className="meta">{t.funding_path ?? "—"}</div>
                    <ThemeStatusActions
                      id={t.id}
                      status={t.status}
                      consultationId={t.consultation_id}
                    />
                    <EnqueueJobButton
                      jobType="theme_preview"
                      title={`preview ${t.title}`}
                      payload={{ theme_id: t.id }}
                      label="プレビュー"
                    />
                    {t.status === "approved" || t.status === "executing" ? (
                      <EnqueueJobButton
                        jobType="theme_execute_assist"
                        title={`execute ${t.title}`}
                        payload={{ theme_id: t.id }}
                        label="完走アシスト"
                      />
                    ) : null}
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
