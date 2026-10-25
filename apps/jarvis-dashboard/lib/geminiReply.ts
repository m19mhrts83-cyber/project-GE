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
  options: { maxAttempts?: number; timeoutMs?: number; maxOutputTokens?: number } = {},
): Promise<GeminiReplyResult> {
  const key = geminiApiKey();
  if (!key) {
    return {
      ok: false,
      error: "GEMINI_API_KEY 未設定。Vercel の環境変数に設定してください。",
    };
  }

  let lastErr = "";
  const models = geminiModels().slice(0, options.maxAttempts ?? 5);
  for (const model of models) {
    const url =
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=` +
      encodeURIComponent(key);
    let res: Response;
    try {
      res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ role: "user", parts }],
        ...(options.maxOutputTokens ? { generationConfig: { maxOutputTokens: options.maxOutputTokens } } : {}),
      }),
      signal: AbortSignal.timeout(options.timeoutMs ?? 30_000),
      });
    } catch {
      lastErr = `${model}: 通信失敗または時間切れ`;
      break; // 同じ通信障害で別モデルを連続起動しない
    }
    if (!res.ok) {
      // 外部エラー本文には入力や秘密が含まれうるため表示しない。
      lastErr = `${model} (HTTP ${res.status})`;
      if (res.status !== 404) break; // 認証・上限・サーバ障害はモデル変更で再試行しない
      continue;
    }
    let data: {
      candidates?: { content?: { parts?: { text?: string }[] } }[];
    };
    try {
      data = await res.json();
    } catch {
      lastErr = `${model}: 応答の読取失敗`;
      break;
    }
    if (!data || !Array.isArray(data.candidates)) {
      lastErr = `${model}: 応答形式が不正`;
      break;
    }
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
  options?: { maxAttempts?: number; timeoutMs?: number; maxOutputTokens?: number },
): Promise<GeminiReplyResult> {
  return geminiGenerate([{ text: prompt }], options);
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
