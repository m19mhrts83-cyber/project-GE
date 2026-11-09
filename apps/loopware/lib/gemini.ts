/** Gemini で文面を作る（サーバ専用。モデルのフォールバックつき）。jarvis-dashboard/lib/geminiReply.ts と同じ作り */

export type GenResult = { ok: true; text: string; model: string } | { ok: false; error: string };

function models(): string[] {
  return [(process.env.GEMINI_MODEL || "").trim(), "gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.0-flash"].filter(
    (m, i, arr) => m && arr.indexOf(m) === i,
  );
}

export async function geminiText(prompt: string, timeoutMs = 45_000): Promise<GenResult> {
  const key = (process.env.GEMINI_API_KEY || "").trim();
  if (!key) return { ok: false, error: "GEMINI_API_KEY 未設定（Vercel の環境変数に入れてください）" };
  let last = "";
  for (const model of models()) {
    let res: Response;
    try {
      res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(key)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contents: [{ role: "user", parts: [{ text: prompt }] }],
            generationConfig: { responseMimeType: "application/json", temperature: 0.2 },
          }),
          signal: AbortSignal.timeout(timeoutMs),
        },
      );
    } catch {
      last = `${model}: 通信失敗または時間切れ`;
      break;
    }
    if (!res.ok) {
      // 外部エラー本文には入力が含まれうるため出さない
      last = `${model} (HTTP ${res.status})`;
      if (res.status !== 404) break;
      continue;
    }
    try {
      const data = (await res.json()) as { candidates?: { content?: { parts?: { text?: string }[] } }[] };
      const text = (data.candidates?.[0]?.content?.parts || []).map((p) => p.text || "").join("").trim();
      if (text) return { ok: true, text, model };
      last = `${model}: 応答が空`;
    } catch {
      last = `${model}: 応答の読取失敗`;
      break;
    }
  }
  return { ok: false, error: `AI で直せませんでした: ${last || "モデルなし"}` };
}
