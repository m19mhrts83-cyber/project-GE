import { NextResponse } from "next/server";
import { loadKnowledge, searchKnowledge } from "@/lib/knowledge";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as { query?: string } | null;
  const query = String(body?.query ?? "").trim();
  if (!query) {
    return NextResponse.json({ hits: [] });
  }

  const rows = await loadKnowledge();
  const hits = searchKnowledge(rows, query, 10).map((h) => ({
    commentId: h.commentId,
    postedAt: h.postedAt ?? null,
    authorName: h.authorName ?? null,
    sourceType: h.sourceType ?? null,
    snippet: h.snippet,
    score: h.score
  }));

  return NextResponse.json({ hits });
}

