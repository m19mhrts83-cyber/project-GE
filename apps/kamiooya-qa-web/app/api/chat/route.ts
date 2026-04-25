import { NextResponse } from "next/server";
import { loadKnowledge, searchKnowledge } from "@/lib/knowledge";

export const runtime = "nodejs";

type ChatRequest = {
  message?: string;
};

function buildAnswerFallback(message: string, hits: ReturnType<typeof searchKnowledge>) {
  const lines: string[] = [];
  lines.push("以下は参照データ内で一致度が高い箇所です。");
  lines.push("");
  for (const h of hits.slice(0, 5)) {
    lines.push(
      `- [${h.sourceType ?? "不明"}] ${h.postedAt ?? ""} ${h.authorName ?? ""} #${h.commentId}`
    );
    lines.push(`  - ${h.snippet}`);
  }
  lines.push("");
  lines.push("質問をもう少し具体化すると、より絞り込めます。");
  return lines.join("\n");
}

async function callOpenAIAnswer(message: string, hits: ReturnType<typeof searchKnowledge>) {
  const apiKey = process.env.OPENAI_API_KEY?.trim();
  if (!apiKey) return null;

  const context = hits
    .slice(0, 8)
    .map((h) => {
      const meta = [
        `source=${h.sourceType ?? "不明"}`,
        `postedAt=${h.postedAt ?? "不明"}`,
        `author=${h.authorName ?? "不明"}`,
        `commentId=${h.commentId}`
      ].join(" | ");
      return `【${meta}】\n${h.content}`;
    })
    .join("\n\n---\n\n");

  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model: process.env.OPENAI_MODEL || "gpt-4o-mini",
      temperature: 0.2,
      messages: [
        {
          role: "system",
          content:
            "あなたは『神・大家さん倶楽部』の情報Q&Aアシスタントです。必ず与えられた参照テキストを根拠に、日本語で簡潔に答えてください。推測は避け、根拠が薄い場合は『参照内で確証が取れない』と明記してください。"
        },
        {
          role: "user",
          content:
            `質問:\n${message}\n\n参照（抜粋）:\n${context}\n\n要件:\n- 参照から結論と根拠を箇条書き\n- 参照に基づく注意点があれば追記\n`
        }
      ]
    })
  });

  if (!res.ok) return null;
  const json = (await res.json().catch(() => null)) as any;
  const text = json?.choices?.[0]?.message?.content;
  return typeof text === "string" ? text : null;
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as ChatRequest | null;
  const message = String(body?.message ?? "").trim();
  if (!message) {
    return NextResponse.json({ answer: "質問が空です。", citations: [] });
  }

  const rows = await loadKnowledge();
  const hits = searchKnowledge(rows, message, 12);

  const ai = await callOpenAIAnswer(message, hits);
  const answer = ai ?? buildAnswerFallback(message, hits);

  const citations = hits.slice(0, 8).map((h) => ({
    commentId: h.commentId,
    postedAt: h.postedAt ?? null,
    authorName: h.authorName ?? null,
    sourceType: h.sourceType ?? null,
    snippet: h.snippet
  }));

  return NextResponse.json({ answer, citations, usedAI: Boolean(ai) });
}

