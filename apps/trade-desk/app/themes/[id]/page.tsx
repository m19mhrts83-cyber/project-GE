import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import EnsureThemeConsultButton from "@/components/EnsureThemeConsultButton";
import ThemeConsultApprove from "@/components/ThemeConsultApprove";
import ThemeStatusActions from "@/components/ThemeStatusActions";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function ThemeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: theme } = await supabase
    .from("kurashift_themes")
    .select(
      "id, title, hypothesis, amount_jpy, duration_note, funding_path, status, review_note, consultation_id, created_at, updated_at, payload"
    )
    .eq("id", id)
    .maybeSingle();

  if (!theme) notFound();

  let consultation: {
    id: string;
    title: string;
    body: string;
    status: string;
    decision: string | null;
    updated_at: string | null;
  } | null = null;

  if (theme.consultation_id) {
    const { data } = await supabase
      .from("kurashift_consultations")
      .select("id, title, body, status, decision, updated_at")
      .eq("id", theme.consultation_id)
      .maybeSingle();
    consultation = data;
  }

  return (
    <Shell active="/themes" email={user?.email ?? null}>
      <p className="meta" style={{ marginBottom: 8 }}>
        <a href="/themes">← テーマ一覧</a>
        {consultation ? (
          <>
            {" · "}
            <a href={`/consultations/${consultation.id}`}>相談記録</a>
          </>
        ) : null}
      </p>
      <h1>{theme.title}</h1>
      <p className="sub">
        状態: <strong>{theme.status}</strong>
        {theme.status === "consulting"
          ? " — 下の相談内容を確認してから承認してください"
          : null}
      </p>

      <div className="card">
        <header>
          <span className="lvl">Theme</span>
          <strong>提案内容</strong>
        </header>
        <dl style={{ margin: 0 }}>
          <dt className="meta">仮説・内容</dt>
          <dd style={{ whiteSpace: "pre-wrap", margin: "0 0 12px" }}>
            {theme.hypothesis || "—"}
          </dd>
          <dt className="meta">金額</dt>
          <dd style={{ margin: "0 0 12px" }}>
            {theme.amount_jpy != null ? fmtYen(Number(theme.amount_jpy)) : "—"}
          </dd>
          <dt className="meta">期間／経路</dt>
          <dd className="meta" style={{ margin: 0 }}>
            {theme.duration_note || "—"} / {theme.funding_path || "—"}
          </dd>
        </dl>
        {theme.status !== "consulting" ? (
          <ThemeStatusActions
            id={theme.id}
            status={theme.status}
            consultationId={theme.consultation_id}
          />
        ) : null}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">相談</span>
          <strong>
            {consultation ? consultation.title : "相談メモ未作成"}
          </strong>
        </header>
        {consultation ? (
          <>
            <p className="meta" style={{ marginTop: 0 }}>
              相談状態: {consultation.status}
              {consultation.decision
                ? ` · 判断: ${consultation.decision}`
                : ""}
            </p>
            <div
              style={{
                whiteSpace: "pre-wrap",
                background: "var(--card-soft)",
                padding: 14,
                borderRadius: 8,
                border: "1px solid var(--line)",
                lineHeight: 1.65,
              }}
            >
              {consultation.body}
            </div>
          </>
        ) : (
          <>
            <p className="meta">
              まだ相談レコードがありません。「相談メモを作成」でテーマ内容から作れます。
            </p>
            <EnsureThemeConsultButton themeId={theme.id} />
          </>
        )}

        <ThemeConsultApprove
          themeId={theme.id}
          themeStatus={theme.status}
        />
      </div>

      {(theme.status === "approved" || theme.status === "executing") && (
        <div style={{ marginTop: 16 }}>
          <EnqueueJobButton
            jobType="theme_preview"
            title={`preview ${theme.title}`}
            payload={{ theme_id: theme.id }}
            label="プレビュー"
          />
          <EnqueueJobButton
            jobType="theme_execute_assist"
            title={`execute ${theme.title}`}
            payload={{ theme_id: theme.id }}
            label="完走アシスト"
          />
        </div>
      )}
    </Shell>
  );
}
