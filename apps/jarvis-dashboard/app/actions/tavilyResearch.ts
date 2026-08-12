"use server";

import { createClient } from "@/lib/supabase/server";

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
    const cached = await researchFromStore(q);
    if (cached) return cached;
    return {
      ok: false,
      error:
        "Tavily オフライン（キー未設定）。KURASHIFT の蓄積も見つかりませんでした",
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
      const cached = await researchFromStore(q);
      if (cached) return cached;
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
    const cached = await researchFromStore(q);
    if (cached) return cached;
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Tavily リクエスト失敗",
    };
  }
}

async function researchFromStore(q: string): Promise<TavilyResearchResult | null> {
  try {
    const supabase = await createClient();
    const { data } = await supabase
      .from("trade_research")
      .select("topic,summary,url,source,fetched_at")
      .order("fetched_at", { ascending: false })
      .limit(30);
    const needle = q.toLowerCase();
    const hits = (data || []).filter((r) => {
      const blob = `${r.topic || ""} ${r.summary || ""}`.toLowerCase();
      return needle.split(/\s+/).some((w) => w.length >= 2 && blob.includes(w));
    });
    const use = hits.length ? hits.slice(0, 5) : (data || []).slice(0, 3);
    if (!use.length) return null;
    const block = [
      "【Tavilyキャッシュ（オフライン）】",
      `クエリ: ${q}`,
      "APIに繋がらなかったため、KURASHIFT 蓄積から拾いました。",
      use
        .map((r) => `- [${r.source}/${r.topic}] ${(r.summary || "").slice(0, 180)}`)
        .join("\n"),
    ].join("\n\n");
    return {
      ok: true,
      query: q,
      block,
      sources: use
        .filter((r) => r.url)
        .map((r) => ({ title: `${r.topic}（蓄積）`, url: r.url || "" })),
    };
  } catch {
    return null;
  }
}
