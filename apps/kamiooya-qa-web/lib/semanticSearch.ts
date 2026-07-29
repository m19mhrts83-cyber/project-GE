import { supabaseAdmin } from "@/lib/supabaseAdmin";

export type SemanticCommentHit = {
  source_type: string | null;
  comment_id: string | null;
  posted_at: string | null;
  author_name: string | null;
  content: string;
  similarity: number;
};

export type SemanticChunkHit = {
  chunk_key: string;
  source_id: number | null;
  start_sec: number | null;
  end_sec: number | null;
  speaker: string | null;
  content: string;
  similarity: number;
};

export type SemanticSourceHit = {
  id: number;
  source_key: string;
  title: string;
  video_url: string | null;
  origin_path: string | null;
  content_channel: string | null;
};

export type SemanticSearchPayload = {
  relatedComments: SemanticCommentHit[];
  relatedChunks: Array<SemanticChunkHit & { source_key?: string | null }>;
  relatedSources: SemanticSourceHit[];
};

type SearchOptions = {
  commentLimit?: number;
  chunkLimit?: number;
  matchThreshold?: number;
};

type GeminiEmbeddingResponse = {
  embedding?: {
    values?: number[];
  };
};

const GEMINI_EMBED_MODEL = "gemini-embedding-001";
const GEMINI_EMBED_DIM = 768;
const GEMINI_EMBED_URL =
  `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_EMBED_MODEL}:embedContent`;

function requireEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing env: ${name}`);
  return value;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function asNullableNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function normalizeContent(value: unknown): string {
  return asString(value).replace(/\s+/g, " ").trim();
}

function buildSnippet(value: unknown, limit = 240): string {
  return normalizeContent(value).slice(0, limit);
}

async function embedQuery(query: string): Promise<number[]> {
  const apiKey = requireEnv("GEMINI_API_KEY");
  const response = await fetch(`${GEMINI_EMBED_URL}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: `models/${GEMINI_EMBED_MODEL}`,
      content: {
        parts: [{ text: query }],
      },
      taskType: "RETRIEVAL_QUERY",
      outputDimensionality: GEMINI_EMBED_DIM,
    }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Gemini embedding failed: HTTP ${response.status} ${text.slice(0, 240)}`);
  }
  const json = (await response.json()) as GeminiEmbeddingResponse;
  const values = json.embedding?.values;
  if (!Array.isArray(values) || values.length === 0) {
    throw new Error("Gemini embedding response is empty");
  }
  return values;
}

export async function semanticSearch(
  query: string,
  options: SearchOptions = {}
): Promise<SemanticSearchPayload> {
  const text = query.trim();
  if (!text) {
    return { relatedComments: [], relatedChunks: [], relatedSources: [] };
  }

  const commentLimit = Math.max(1, Math.min(60, options.commentLimit ?? 20));
  const chunkLimit = Math.max(1, Math.min(40, options.chunkLimit ?? 12));
  const matchThreshold = Number.isFinite(options.matchThreshold)
    ? Number(options.matchThreshold)
    : 0.55;

  const embedding = await embedQuery(text);
  const sb = supabaseAdmin();

  const [commentsRpc, chunksRpc] = await Promise.all([
    sb.rpc("match_comments_semantic", {
      query_embedding: embedding,
      match_threshold: matchThreshold,
      match_count: commentLimit,
    }),
    sb.rpc("match_chunks_semantic", {
      query_embedding: embedding,
      match_threshold: matchThreshold,
      match_count: chunkLimit,
    }),
  ]);

  if (commentsRpc.error) {
    throw new Error(`match_comments_semantic failed: ${commentsRpc.error.message}`);
  }
  if (chunksRpc.error) {
    throw new Error(`match_chunks_semantic failed: ${chunksRpc.error.message}`);
  }

  const commentRows = (commentsRpc.data || []).map((row: any) => ({
    source_type: asString(row.source_type) || null,
    comment_id: asString(row.comment_id) || null,
    posted_at: asString(row.posted_at) || null,
    author_name: asString(row.author_name) || null,
    content: buildSnippet(row.content),
    similarity: Number(row.similarity || 0),
  }));

  const chunkRows = (chunksRpc.data || []).map((row: any) => ({
    chunk_key: asString(row.chunk_key),
    source_id: asNullableNumber(row.source_id),
    start_sec: asNullableNumber(row.start_sec),
    end_sec: asNullableNumber(row.end_sec),
    speaker: asString(row.speaker) || null,
    content: buildSnippet(row.content),
    similarity: Number(row.similarity || 0),
  }));

  const sourceIds = Array.from(
    new Set(
      chunkRows
        .map((row: { source_id: number | null }) => row.source_id)
        .filter((value: number | null): value is number => typeof value === "number")
    )
  );

  let relatedSources: SemanticSourceHit[] = [];
  if (sourceIds.length > 0) {
    const { data: sources, error } = await sb
      .from("knowledge_sources")
      .select("id,source_key,title,video_url,origin_path,content_channel")
      .in("id", sourceIds);
    if (error) {
      throw new Error(`knowledge_sources fetch failed: ${error.message}`);
    }
    relatedSources = (sources || []).map((row: any) => ({
      id: Number(row.id),
      source_key: asString(row.source_key),
      title: asString(row.title),
      video_url: asString(row.video_url) || null,
      origin_path: asString(row.origin_path) || null,
      content_channel: asString(row.content_channel) || null,
    }));
  }

  const sourceById = new Map<number, SemanticSourceHit>();
  relatedSources.forEach((source) => sourceById.set(source.id, source));

  const relatedChunks = chunkRows.map((row: SemanticChunkHit) => ({
    ...row,
    source_key: row.source_id != null ? sourceById.get(row.source_id)?.source_key || null : null,
  }));

  return {
    relatedComments: commentRows,
    relatedChunks,
    relatedSources,
  };
}
