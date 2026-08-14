import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { previewKind } from "@/lib/taxEvidence";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function TaxEvidencePreviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data } = await supabase
    .from("kurashift_tax_evidence")
    .select(
      "id, fiscal_year, scope, subject, original_filename, stored_path, storage_path, doc_kind"
    )
    .eq("id", id)
    .maybeSingle();
  if (!data) notFound();

  const filename = data.original_filename || data.stored_path.split("/").pop() || "ファイル";
  const kind = previewKind(filename);
  const src = `/api/tax/evidence/${id}/file`;
  const scopeLabel = data.scope === "corporate" ? "法人" : "個人";
  const kindLabel =
    data.doc_kind === "filed_return"
      ? "確定申告書"
      : data.doc_kind === "re_statement"
        ? "収支内訳書"
        : data.doc_kind === "attachment"
          ? "メール添付"
          : data.doc_kind;

  return (
    <Shell active="/tax" email={user?.email ?? null}>
      <p className="page-kicker">確定申告 · プレビュー</p>
      <h1>{filename}</h1>
      <p className="sub">
        {scopeLabel} {data.fiscal_year}年 · {kindLabel}
        {data.subject ? ` · ${data.subject}` : ""}
      </p>
      <p className="meta" style={{ marginTop: 0 }}>
        ありか: {data.stored_path}
      </p>
      <p style={{ margin: "8px 0 14px" }}>
        <a href="/tax">← 確定申告に戻る</a>
        {" · "}
        <a href={src} target="_blank" rel="noreferrer">
          別タブで開く
        </a>
      </p>

      {kind === "pdf" || kind === "other" ? (
        <iframe
          className="evidence-frame"
          title={filename}
          src={src}
        />
      ) : null}
      {kind === "image" ? (
        <img className="evidence-frame" alt={filename} src={src} />
      ) : null}
      {kind === "text" ? (
        <iframe className="evidence-frame" title={filename} src={src} />
      ) : null}

      {!data.storage_path ? (
        <p className="meta" style={{ marginTop: 12 }}>
          本番のブラウザでは、Storage に上がっていないとプレビューできないことがあります。表示されないときは Jarvis に一声ください。
        </p>
      ) : null}
    </Shell>
  );
}
