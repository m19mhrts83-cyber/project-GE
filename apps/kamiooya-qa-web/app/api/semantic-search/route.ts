import { NextResponse } from "next/server";
import { semanticSearch } from "@/lib/semanticSearch";

export const runtime = "nodejs";

type SemanticSearchRequest = {
  query?: string;
  comment_limit?: number;
  chunk_limit?: number;
  match_threshold?: number;
  secret?: string;
};

function isAuthorized(req: Request, body: SemanticSearchRequest | null): boolean {
  const expected = process.env.SEMANTIC_SEARCH_SHARED_SECRET?.trim();
  if (!expected) return true;
  const headerSecret = req.headers.get("x-semantic-shared-secret")?.trim();
  const bodySecret = String(body?.secret ?? "").trim();
  return headerSecret === expected || bodySecret === expected;
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as SemanticSearchRequest | null;
  if (!isAuthorized(req, body)) {
    return NextResponse.json({ errorMessage: "forbidden" }, { status: 403 });
  }

  const query = String(body?.query ?? "").trim();
  if (!query) {
    return NextResponse.json(
      { relatedComments: [], relatedChunks: [], relatedSources: [] },
      { status: 200 }
    );
  }

  try {
    const result = await semanticSearch(query, {
      commentLimit: Number(body?.comment_limit ?? 20),
      chunkLimit: Number(body?.chunk_limit ?? 12),
      matchThreshold: Number(body?.match_threshold ?? 0.55),
    });
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "semantic_search_failed";
    return NextResponse.json({ errorMessage: message }, { status: 500 });
  }
}
