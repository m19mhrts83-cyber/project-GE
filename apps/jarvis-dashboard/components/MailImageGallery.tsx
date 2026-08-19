import type { MailImagePart } from "@/lib/gmail/fetchMessageParts";
import { imageProxyPath } from "@/lib/gmail/fetchMessageParts";

export default function MailImageGallery({
  triageId,
  images,
}: {
  triageId: string;
  images: MailImagePart[];
}) {
  if (!images.length) return null;
  return (
    <div className="mail-image-gallery">
      <p className="mail-image-gallery-title">図・画像</p>
      <div className="mail-image-grid">
        {images.map((img) => (
          <figure key={img.attachmentId} className="mail-image-fig">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={imageProxyPath(triageId, img.attachmentId)}
              alt={img.filename}
            />
            <figcaption>{img.filename}</figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
}
