import MailImageGallery from "@/components/MailImageGallery";
import type { MailFilePart, MailImagePart } from "@/lib/gmail/fetchMessageParts";
import { imageProxyPath } from "@/lib/gmail/fetchMessageParts";

export default function MailBodyView({
  triageId,
  body,
  bodyJa,
  html,
  images,
  files,
  visualsError,
  open = true,
}: {
  triageId: string;
  body: string | null | undefined;
  bodyJa?: string | null;
  html?: string | null;
  images?: MailImagePart[];
  files?: MailFilePart[];
  visualsError?: string | null;
  open?: boolean;
}) {
  const text = (body || "").trim();
  const ja = (bodyJa || "").trim();
  const imgs = images || [];
  const atts = files || [];
  const hasHtml = Boolean((html || "").trim());

  if (!text && !hasHtml && !imgs.length && !atts.length) {
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

      <MailImageGallery triageId={triageId} images={imgs} />
      {atts.length > 0 ? (
        <div className="mail-file-list">
          <p className="mail-body-label">添付</p>
          <ul>
            {atts.map((f) => (
              <li key={f.attachmentId}>
                <a
                  href={imageProxyPath(triageId, f.attachmentId)}
                  target="_blank"
                  rel="noreferrer"
                >
                  {f.filename}
                </a>
                {f.mimeType ? (
                  <span className="meta"> · {f.mimeType}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {visualsError && !imgs.length && !hasHtml ? (
        <p className="meta mail-visuals-err">{visualsError}</p>
      ) : null}
    </div>
  );
}
