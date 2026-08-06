"use server";

export type TavilyResearchResult =
  | {
      ok: true;
      query: string;
      block: string;
      sources: { title: string; url: string }[];
    }
  | { ok: false; error: string };

/** DraftWorkbench 用。自動送信しない — 文脈テキストのみ返す */
export async function researchWithTavily(
  query: string,
): Promise<TavilyResearchResult> {
  const q = query.trim().slice(0, 400);
  if (q.length < 2) return { ok: false, error: "検索語が短すぎます" };

  const key = (process.env.TAVILY_API_KEY || "").trim();
  if (!key) {
    return {
      ok: false,
      error:
        "TAVILY_API_KEY が未設定です（.env.jarvis_private / Cloud My Secrets）",
    };
  }

  try {
    const res = await fetch("https://api.tavily.com/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: key,
        query: q,
        search_depth: "basic",
        include_answer: true,
        max_results: 5,
      }),
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return {
        ok: false,
        error: `Tavily HTTP ${res.status}${text ? `: ${text.slice(0, 120)}` : ""}`,
      };
    }
    const data = (await res.json()) as {
      answer?: string;
      results?: { title?: string; url?: string; content?: string }[];
    };
    const sources = (data.results || [])
      .filter((r) => r.url)
      .slice(0, 5)
      .map((r) => ({
        title: (r.title || r.url || "").slice(0, 80),
        url: r.url || "",
      }));
    const snippets = (data.results || [])
      .slice(0, 3)
      .map((r, i) => {
        const body = (r.content || "").replace(/\s+/g, " ").trim().slice(0, 220);
        return `${i + 1}. ${r.title || "（無題）"}\n${body}\n${r.url || ""}`;
      })
      .join("\n\n");

    const block = [
      "【Tavily 下調べ】",
      `クエリ: ${q}`,
      data.answer ? `要約: ${data.answer.trim()}` : "",
      snippets ? `抜粋:\n${snippets}` : "",
      sources.length
        ? `出典:\n${sources.map((s) => `- ${s.title}: ${s.url}`).join("\n")}`
        : "",
    ]
      .filter(Boolean)
      .join("\n\n");

    return { ok: true, query: q, block, sources };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Tavily リクエスト失敗",
    };
  }
}
