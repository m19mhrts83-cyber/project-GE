/**
 * 従量課金の Gemini API（2026-11-17・判断デスクの返信だけ）。
 *
 * 普段は Mac の定額 AI（lib/flatAi.ts）を使う。Mac がスリープ等で応答しないときに限り、
 * 松野さんが画面で「Gemini で作る（従量課金）」を押したその1回だけ呼ぶ。自動では呼ばない。
 * 鍵は Vercel の GEMINI_API_KEY（既存）。モデルは GEMINI_MODEL、無ければ flash 系。
 */

export type GeminiPaidResult = { ok: true; text: string; model: string } | { ok: false; error: string };

export function geminiPaidConfigured(): boolean {
  return Boolean((process.env.GEMINI_API_KEY || "").trim());
}

function models(): string[] {
  return [(process.env.GEMINI_MODEL || "").trim(), "gemini-flash-latest", "gemini-2.5-flash"].filter(
    (m, i, a) => m && a.indexOf(m) === i,
  );
}

export async function geminiPaidGenerate(prompt: string, timeoutMs = 40_000): Promise<GeminiPaidResult> {
  const key = (process.env.GEMINI_API_KEY || "").trim();
  if (!key) return { ok: false, error: "GEMINI_API_KEY がダッシュボード（Vercel）にありません" };
  let last = "";
  for (const model of models()) {
    let res: Response;
    try {
      res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "x-goog-api-key": key },
          body: JSON.stringify({ contents: [{ role: "user", parts: [{ text: prompt }] }] }),
          signal: AbortSignal.timeout(timeoutMs),
        },
      );
    } catch {
      return { ok: false, error: `Gemini（${model}）: 通信失敗または時間切れ` };
    }
    if (!res.ok) {
      // 応答本文は入力が混ざりうるので出さない。404（モデル名違い）だけ次のモデルへ
      last = `Gemini（${model}）HTTP ${res.status}`;
      if (res.status === 404) continue;
      return { ok: false, error: last };
    }
    try {
      const data = (await res.json()) as { candidates?: { content?: { parts?: { text?: string }[] } }[] };
      const text = (data.candidates?.[0]?.content?.parts || []).map((p) => p.text || "").join("").trim();
      if (text) return { ok: true, text, model };
      last = `Gemini（${model}）: 応答が空`;
    } catch {
      return { ok: false, error: `Gemini（${model}）: 応答を読めませんでした` };
    }
  }
  return { ok: false, error: last || "Gemini: 使えるモデルがありません" };
}
