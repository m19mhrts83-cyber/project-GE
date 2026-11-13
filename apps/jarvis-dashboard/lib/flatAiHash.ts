import { createHash } from "node:crypto";

export type FlatImage = { mimeType: string; base64: string };

/** 同じ依頼を見分けるための指紋（文面＋画像の大きさと先頭） */
export function flatPromptHash(prompt: string, images: FlatImage[] = []): string {
  const h = createHash("sha256");
  h.update(prompt);
  for (const img of images) h.update(`|${img.mimeType}|${img.base64.length}|${img.base64.slice(0, 64)}`);
  return h.digest("hex");
}
