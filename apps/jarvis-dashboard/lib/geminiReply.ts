/**
 * 文章／画像読み取りの生成（呼び出し口の名前は互換のため geminiReply のまま）。
 *
 * 2026-11-13 から従量課金の Gemini API は使わない。中身は Mac の定額 AI
 * （Codex → Cursor → Claude、lib/flatAi.ts）への依頼。返り値の形は以前と同じ。
 */
import { flatAiGenerate, type FlatImage } from "@/lib/flatAi";

export type GeminiReplyResult =
  | { ok: true; text: string }
  | { ok: false; error: string };

export type GeminiVisionJsonResult =
  | { ok: true; json: Record<string, unknown>; text: string }
  | { ok: false; error: string };

export type GeminiVisionImage = FlatImage;

export type ReplyOptions = {
  /** 互換のため受けるだけ（定額 AI 側で回す順を決める） */
  maxAttempts?: number;
  /** 互換のため受けるだけ */
  timeoutMs?: number;
  maxOutputTokens?: number;
  /** 結果を待つ上限（既定 55 秒）。超えても Mac 側は作り続ける */
  waitMs?: number;
  purpose?: string;
};

export async function geminiReply(prompt: string, options: ReplyOptions = {}): Promise<GeminiReplyResult> {
  const p = options.maxOutputTokens
    ? `${prompt}\n\n（出力はおよそ ${Math.round(options.maxOutputTokens * 0.7)} 字以内）`
    : prompt;
  const r = await flatAiGenerate(p, { purpose: options.purpose, waitMs: options.waitMs });
  return r.ok ? { ok: true, text: r.text } : { ok: false, error: r.error };
}

/** 画像＋プロンプト → JSON オブジェクト（markdown fence 除去） */
export async function geminiVisionJson(
  images: GeminiVisionImage[],
  prompt: string,
  options: ReplyOptions = {},
): Promise<GeminiVisionJsonResult> {
  if (!images.length) {
    return { ok: false, error: "画像がありません" };
  }
  const reply = await flatAiGenerate(prompt, { images, purpose: options.purpose || "vision", waitMs: options.waitMs });
  if (!reply.ok) return { ok: false, error: reply.error };

  let raw = reply.text.trim();
  const fence = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) raw = fence[1].trim();
  else {
    const obj = raw.match(/\{[\s\S]*\}/);
    if (obj) raw = obj[0];
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false, error: "画像読み取りの応答がオブジェクト JSON ではありません" };
    }
    return { ok: true, json: parsed as Record<string, unknown>, text: reply.text };
  } catch {
    return { ok: false, error: `画像読み取りの JSON を読めませんでした: ${raw.slice(0, 120)}` };
  }
}
