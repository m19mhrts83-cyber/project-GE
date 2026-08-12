import Shell from "@/components/Shell";
import ThemeConsultApprove from "@/components/ThemeConsultApprove";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function ConsultationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: row } = await supabase
    .from("kurashift_consultations")
    .select(
      "id, title, body, lane, decision, status, metadata, created_at, updated_at"
    )
    .eq("id", id)
    .maybeSingle();

  if (!row) notFound();

  const metaThemeId =
    row.metadata &&
    typeof row.metadata === "object" &&
    "theme_id" in row.metadata
      ? String((row.metadata as { theme_id?: string }).theme_id || "")
      : "";

  const { data: linkedThemes } = await supabase
    .from("kurashift_themes")
    .select(
      "id, title, hypothesis, amount_jpy, status, consultation_id, funding_path"
    )
    .or(
      metaThemeId
        ? `consultation_id.eq.${id},id.eq.${metaThemeId}`
        : `consultation_id.eq.${id}`
    )
    .limit(5);

  const theme = (linkedThemes ?? [])[0] ?? null;

  return (
    <Shell active="/consultations" email={user?.email ?? null}>
      <p className="meta" style={{ marginBottom: 8 }}>
        <a href="/consultations">← 相談一覧</a>
        {theme ? (
          <>
            {" · "}
            <a href={`/themes/${theme.id}`}>テーマ詳細</a>
          </>
        ) : null}
      </p>
      <h1>{row.title}</h1>
      <p className="sub">
        {row.lane} · {row.status}
        {row.decision ? ` · 判断: ${row.decision}` : ""}
      </p>

      <div className="card">
        <header>
          <span className="lvl">相談本文</span>
          <strong>内容確認</strong>
        </header>
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
          {row.body}
        </div>
        <p className="meta" style={{ marginBottom: 0 }}>
          更新: {row.updated_at?.slice(0, 19) ?? "—"}
        </p>
      </div>

      {theme ? (
        <div className="card" style={{ marginTop: 16 }}>
          <header>
            <span className="lvl">紐づくテーマ</span>
            <strong>{theme.title}</strong>
          </header>
          <p className="meta" style={{ marginTop: 0 }}>
            状態: <strong>{theme.status}</strong>
            {theme.amount_jpy != null
              ? ` · ${fmtYen(Number(theme.amount_jpy))}`
              : ""}
            {theme.funding_path ? ` · ${theme.funding_path}` : ""}
          </p>
          <div className="meta" style={{ whiteSpace: "pre-wrap" }}>
            {theme.hypothesis}
          </div>
          <ThemeConsultApprove
            themeId={theme.id}
            themeStatus={theme.status}
          />
        </div>
      ) : (
        <p className="meta" style={{ marginTop: 16 }}>
          テーマ未リンクの相談です。テーマ側で「相談中へ」すると自動で紐づきます。
        </p>
      )}
    </Shell>
  );
}
