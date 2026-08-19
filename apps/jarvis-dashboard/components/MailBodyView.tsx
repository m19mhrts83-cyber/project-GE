import MailImageGallery from "@/components/MailImageGallery";
import type { MailImagePart } from "@/lib/gmail/fetchMessageParts";

export default function MailBodyView({
  triageId,
  body,
  bodyJa,
  html,
  images,
  visualsError,
  open = true,
}: {
  triageId: string;
  body: string | null | undefined;
  bodyJa?: string | null;
  html?: string | null;
  images?: MailImagePart[];
  visualsError?: string | null;
  open?: boolean;
}) {
  const text = (body || "").trim();
  const ja = (bodyJa || "").trim();
  const imgs = images || [];
  const hasHtml = Boolean((html || "").trim());
  const gallery = hasHtml ? imgs.filter((i) => !i.inline) : imgs;

  if (!text && !hasHtml && !imgs.length) {
    return (
      <p className="empty" style={{ padding: "8px 0" }}>
        （元メール本文は未保存。次回の Mac 夜間バッチ／GHA 取得後に表示されます）
      </p>
    );
  }

  return (
    <div className="mail-body-view">
      {ja ? (
        <>
          <p className="mail-body-label">和訳</p>
          <pre className="orig-body">{ja}</pre>
        </>
      ) : null}

      {hasHtml ? (
        <>
          <p className="mail-body-label">{ja ? "原文（図つき）" : "本文"}</p>
          <div
            className="mail-html-body orig-body"
            dangerouslySetInnerHTML={{ __html: html || "" }}
          />
        </>
      ) : text ? (
        <details open={open} className="orig-details">
          <summary>{ja ? "原文" : "元メール全文"}</summary>
          <pre className="orig-body">{text}</pre>
        </details>
      ) : null}

      <MailImageGallery triageId={triageId} images={gallery} />
      {visualsError && !imgs.length && !hasHtml ? (
        <p className="meta mail-visuals-err">{visualsError}</p>
      ) : null}
    </div>
  );
}
