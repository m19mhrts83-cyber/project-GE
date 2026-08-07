/** Gemini テキスト／Vision 生成（モデルフォールバック付き） */

export type GeminiReplyResult =
  | { ok: true; text: string }
  | { ok: false; error: string };

export type GeminiVisionJsonResult =
  | { ok: true; json: Record<string, unknown>; text: string }
  | { ok: false; error: string };

export type GeminiVisionImage = {
  mimeType: string;
  base64: string;
};

function geminiApiKey(): string {
  return (process.env.GEMINI_API_KEY || "").trim();
}

function geminiModels(): string[] {
  return [
    (process.env.GEMINI_MODEL || "").trim(),
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-flash-lite-latest",
    "gemini-2.0-flash",
  ].filter((m, i, arr) => m && arr.indexOf(m) === i);
}

async function geminiGenerate(
  parts: Array<Record<string, unknown>>,
): Promise<GeminiReplyResult> {
  const key = geminiApiKey();
  if (!key) {
    return {
      ok: false,
      error: "GEMINI_API_KEY 未設定。Vercel の環境変数に設定してください。",
    };
  }

  let lastErr = "";
  for (const model of geminiModels()) {
    const url =
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=` +
      encodeURIComponent(key);
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ role: "user", parts }],
      }),
    });
    if (!res.ok) {
      const t = await res.text();
      lastErr = `${model} (${res.status}): ${t.slice(0, 160)}`;
      continue;
    }
    const data = (await res.json()) as {
      candidates?: { content?: { parts?: { text?: string }[] } }[];
    };
    const text =
      data.candidates?.[0]?.content?.parts?.map((p) => p.text || "").join("") ||
      "";
    const out = text.trim();
    if (!out) {
      lastErr = `${model}: 応答が空`;
      continue;
    }
    return { ok: true, text: out };
  }
  return {
    ok: false,
    error: `Gemini 失敗: ${lastErr || "利用可能なモデルなし"}`,
  };
}

export async function geminiReply(
  prompt: string,
): Promise<GeminiReplyResult> {
  return geminiGenerate([{ text: prompt }]);
}

/** 画像＋プロンプト → JSON オブジェクト（markdown fence 除去） */
export async function geminiVisionJson(
  images: GeminiVisionImage[],
  prompt: string,
): Promise<GeminiVisionJsonResult> {
  if (!images.length) {
    return { ok: false, error: "画像がありません" };
  }
  const parts: Array<Record<string, unknown>> = [
    { text: prompt },
    ...images.map((img) => ({
      inline_data: {
        mime_type: img.mimeType || "image/jpeg",
        data: img.base64,
      },
    })),
  ];
  const reply = await geminiGenerate(parts);
  if (!reply.ok) return reply;

  let raw = reply.text.trim();
  const fence = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) raw = fence[1].trim();
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false, error: "Vision 応答がオブジェクト JSON ではありません" };
    }
    return {
      ok: true,
      json: parsed as Record<string, unknown>,
      text: reply.text,
    };
  } catch {
    return {
      ok: false,
      error: `Vision JSON パース失敗: ${raw.slice(0, 120)}`,
    };
  }
}
