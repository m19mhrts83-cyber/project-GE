/** Gemini テキスト生成（モデルフォールバック付き） */

export type GeminiReplyResult =
  | { ok: true; text: string }
  | { ok: false; error: string };

export async function geminiReply(
  prompt: string,
): Promise<GeminiReplyResult> {
  const key = (process.env.GEMINI_API_KEY || "").trim();
  if (!key) {
    return {
      ok: false,
      error: "GEMINI_API_KEY 未設定。Vercel の環境変数に設定してください。",
    };
  }
  const models = [
    (process.env.GEMINI_MODEL || "").trim(),
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-flash-lite-latest",
    "gemini-2.0-flash",
  ].filter((m, i, arr) => m && arr.indexOf(m) === i);

  let lastErr = "";
  for (const model of models) {
    const url =
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=` +
      encodeURIComponent(key);
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: prompt }] }],
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
