/**
 * トリアージ詳細向け: Gmail 本文 HTML と画像パートをその場で取る。
 * バイナリは jsonb に保存せず、認証付きプロキシで配信する。
 */
import type { gmail_v1 } from "googleapis";
import { gmailClientFromEnv } from "./clientFromEnv";

const MAX_IMAGES = 8;
const MAX_FILES = 8;
const MIN_IMAGE_BYTES = 200;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const IMAGE_MIME = /^(image\/(png|jpe?g|gif|webp|bmp))$/i;
const FILE_MIME =
  /^(application\/pdf|application\/zip|application\/octet-stream|text\/csv|application\/vnd\.)/i;

export type MailImagePart = {
  attachmentId: string;
  filename: string;
  mimeType: string;
  contentId: string | null;
  inline: boolean;
  size: number;
};

export type MailFilePart = {
  attachmentId: string;
  filename: string;
  mimeType: string;
  size: number;
};

export type MailVisuals = {
  html: string | null;
  images: MailImagePart[];
  files: MailFilePart[];
  error?: string;
};

type Part = gmail_v1.Schema$MessagePart;

function headerMap(part: Part): Record<string, string> {
  const out: Record<string, string> = {};
  for (const h of part.headers || []) {
    const name = (h.name || "").toLowerCase();
    if (name) out[name] = h.value || "";
  }
  return out;
}

function decodeData(data: string | null | undefined): string {
  if (!data) return "";
  try {
    const buf = Buffer.from(data.replace(/-/g, "+").replace(/_/g, "/"), "base64");
    return buf.toString("utf8");
  } catch {
    return "";
  }
}

function walkParts(part: Part | undefined, acc: Part[]): void {
  if (!part) return;
  acc.push(part);
  for (const p of part.parts || []) walkParts(p, acc);
}

function contentIdOf(part: Part): string | null {
  const h = headerMap(part);
  const raw = (h["content-id"] || "").trim();
  if (!raw) return null;
  return raw.replace(/^<|>$/g, "").trim() || null;
}

function isInline(part: Part): boolean {
  const disp = (headerMap(part)["content-disposition"] || "").toLowerCase();
  return disp.includes("inline") || Boolean(contentIdOf(part));
}

export function sanitizeMailHtml(
  html: string,
  cidToSrc: Record<string, string>,
): string {
  let s = html
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, "")
    .replace(/<object[\s\S]*?<\/object>/gi, "")
    .replace(/<embed[\s\S]*?>/gi, "")
    .replace(/<link[\s\S]*?>/gi, "")
    .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, "")
    .replace(/javascript:/gi, "");

  s = s.replace(
    /src\s*=\s*(["'])\s*cid:([^"']+)\1/gi,
    (_m, q: string, cid: string) => {
      const key = cid.replace(/^<|>$/g, "").trim();
      const src = cidToSrc[key] || cidToSrc[key.toLowerCase()];
      return src ? `src=${q}${src}${q}` : `src=${q}${q}`;
    },
  );

  // 外部トラッキングピクセルは残しすぎないが、図の CDN は許可（https のみ）
  s = s.replace(
    /src\s*=\s*(["'])(?!https?:|data:|\/api\/)[^"']*\1/gi,
    'src="#"',
  );
  return s;
}

export function imageProxyPath(
  triageId: string,
  attachmentId: string,
): string {
  const id = encodeURIComponent(triageId);
  const aid = encodeURIComponent(attachmentId);
  return `/api/mail/${id}/image?aid=${aid}`;
}

export async function fetchMailVisuals(opts: {
  triageId: string;
  gmailMessageId?: string | null;
  account?: string | null;
}): Promise<MailVisuals> {
  const gid = String(opts.gmailMessageId || "").trim();
  if (!gid) {
    return { html: null, images: [], files: [] };
  }
  const client = gmailClientFromEnv(opts.account);
  if (!client.ok) {
    return {
      html: null,
      images: [],
      files: [],
      error: "Gmail トークンが無く図を取得できません（Gmail を開いて確認）",
    };
  }
  try {
    const res = await client.gmail.users.messages.get({
      userId: "me",
      id: gid,
      format: "full",
    });
    const parts: Part[] = [];
    walkParts(res.data.payload, parts);

    const images: MailImagePart[] = [];
    const files: MailFilePart[] = [];
    let htmlRaw = "";
    for (const part of parts) {
      const mime = (part.mimeType || "").toLowerCase();
      const size = Number(part.body?.size || 0);
      if (mime === "text/html") {
        const decoded = decodeData(part.body?.data);
        if (decoded.length > htmlRaw.length) htmlRaw = decoded;
      }
      const aid = String(part.body?.attachmentId || "").trim();
      if (!aid) continue;
      if (IMAGE_MIME.test(mime)) {
        if (size && (size < MIN_IMAGE_BYTES || size > MAX_IMAGE_BYTES)) continue;
        if (images.length >= MAX_IMAGES) continue;
        const filename =
          (part.filename || "").trim() ||
          `image-${images.length + 1}.${mime.split("/")[1] || "png"}`;
        images.push({
          attachmentId: aid,
          filename,
          mimeType: mime,
          contentId: contentIdOf(part),
          inline: isInline(part),
          size,
        });
        continue;
      }
      const fname = (part.filename || "").trim();
      if (!fname) continue;
      const looksPdf = /\.pdf$/i.test(fname) || mime === "application/pdf";
      if (!(looksPdf || FILE_MIME.test(mime))) continue;
      if (size && size > MAX_FILE_BYTES) continue;
      if (files.length >= MAX_FILES) continue;
      files.push({
        attachmentId: aid,
        filename: fname,
        mimeType: mime || "application/octet-stream",
        size,
      });
    }

    const cidToSrc: Record<string, string> = {};
    for (const img of images) {
      const src = imageProxyPath(opts.triageId, img.attachmentId);
      if (img.contentId) {
        cidToSrc[img.contentId] = src;
        cidToSrc[img.contentId.toLowerCase()] = src;
      }
    }
    const html = htmlRaw
      ? sanitizeMailHtml(htmlRaw.slice(0, 200_000), cidToSrc)
      : null;
    return { html, images, files };
  } catch (e) {
    return {
      html: null,
      images: [],
      files: [],
      error: `図の取得に失敗しました: ${e instanceof Error ? e.message : String(e)}`.slice(
        0,
        200,
      ),
    };
  }
}

export async function fetchMailAttachmentBytes(opts: {
  gmailMessageId: string;
  attachmentId: string;
  account?: string | null;
}): Promise<
  | { ok: true; bytes: Buffer; mimeType: string; filename?: string }
  | { ok: false; error: string }
> {
  const client = gmailClientFromEnv(opts.account);
  if (!client.ok) return { ok: false, error: client.error };
  try {
    const msg = await client.gmail.users.messages.get({
      userId: "me",
      id: opts.gmailMessageId,
      format: "full",
    });
    const parts: Part[] = [];
    walkParts(msg.data.payload, parts);
    const part = parts.find(
      (p) => String(p.body?.attachmentId || "") === opts.attachmentId,
    );
    if (!part) return { ok: false, error: "attachment not in message" };
    const mime = (part.mimeType || "application/octet-stream").toLowerCase();
    const fname = (part.filename || "").trim();
    const isImage = IMAGE_MIME.test(mime);
    const isFile =
      /\.pdf$/i.test(fname) ||
      mime === "application/pdf" ||
      FILE_MIME.test(mime);
    if (!isImage && !isFile) {
      return { ok: false, error: "unsupported part" };
    }
    const att = await client.gmail.users.messages.attachments.get({
      userId: "me",
      messageId: opts.gmailMessageId,
      id: opts.attachmentId,
    });
    const data = att.data.data;
    if (!data) return { ok: false, error: "empty attachment" };
    const bytes = Buffer.from(
      data.replace(/-/g, "+").replace(/_/g, "/"),
      "base64",
    );
    const max = isImage ? MAX_IMAGE_BYTES : MAX_FILE_BYTES;
    const min = isImage ? MIN_IMAGE_BYTES : 1;
    if (bytes.length < min || bytes.length > max) {
      return { ok: false, error: "size skipped" };
    }
    return {
      ok: true,
      bytes,
      mimeType: mime,
      filename: fname || undefined,
    };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}
