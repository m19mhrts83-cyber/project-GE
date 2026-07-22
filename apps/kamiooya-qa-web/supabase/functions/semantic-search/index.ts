// Supabase Edge Function: semantic search + answer summary.
// Auth: X-Semantic-Shared-Secret (or body.secret). Deploy with --no-verify-jwt.
//
// Thoroughness over speed: recall at least as many hits as normal search (100/50),
// blend recent posts into answer context, allow longer summaries (within ~150s wall clock).

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const GEMINI_EMBED_MODEL = "gemini-embedding-001";
const GEMINI_ANSWER_MODEL = "gemini-3-flash-preview";
const GEMINI_EMBED_DIM = 768;
const GEMINI_EMBED_URL =
  `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_EMBED_MODEL}:embedContent`;
const GEMINI_GENERATE_URL =
  `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_ANSWER_MODEL}:generateContent`;
const SNIPPET_LIMIT = 800;
const ANSWER_SNIPPET_LIMIT = 600;
const DEFAULT_MATCH_THRESHOLD = 0.22;
const DEFAULT_COMMENT_LIMIT = 100;
const DEFAULT_CHUNK_LIMIT = 50;
const MAX_COMMENT_LIMIT = 150;
const MAX_CHUNK_LIMIT = 80;
const ANSWER_COMMENT_LIMIT = 50;
const ANSWER_CHUNK_LIMIT = 25;
const REFUSAL =
  "参照内で確証が取れないため、お答えすることができません。";

type SemanticSearchRequest = {
  query?: string;
  comment_limit?: number;
  chunk_limit?: number;
  match_threshold?: number;
  skip_answer?: boolean;
  secret?: string;
  session_id?: string;
  user_id?: string;
};

type CommentRow = {
  source_type: string | null;
  comment_id: string | null;
  posted_at: string | null;
  author_name: string | null;
  content: string;
  similarity: number;
};

type ChunkRow = {
  chunk_key: string;
  source_id: number | null;
  start_sec: number | null;
  end_sec: number | null;
  speaker: string | null;
  content: string;
  similarity: number;
  source_key?: string | null;
};

function corsHeaders(): HeadersInit {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers":
      "authorization, x-client-info, apikey, content-type, x-semantic-shared-secret",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
  };
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders(), "Content-Type": "application/json" },
  });
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function asNullableNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function buildSnippet(value: unknown, limit = SNIPPET_LIMIT): string {
  return asString(value).replace(/\s+/g, " ").trim().slice(0, limit);
}

function isAuthorized(req: Request, body: SemanticSearchRequest | null): boolean {
  const expected = (Deno.env.get("SEMANTIC_SEARCH_SHARED_SECRET") || "").trim();
  if (!expected) return true;
  const headerSecret = (req.headers.get("x-semantic-shared-secret") || "").trim();
  const bodySecret = asString(body?.secret).trim();
  return headerSecret === expected || bodySecret === expected;
}

function commentKey(row: CommentRow): string {
  return asString(row.comment_id) || `${row.posted_at}|${row.author_name}|${row.content.slice(0, 40)}`;
}

function postedAtMs(value: string | null): number {
  if (!value) return 0;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : 0;
}

/** Prefer posted_at; if missing (common), use numeric comment_id as recency proxy. */
function recencyScore(row: CommentRow): number {
  const fromDate = postedAtMs(row.posted_at);
  if (fromDate > 0) return fromDate;
  const idNum = Number(asString(row.comment_id));
  // Scale id into a comparable range (ids are ~1..30k)
  if (Number.isFinite(idNum) && idNum > 0) return idNum;
  return 0;
}

/** Similarity-first list, then fill with newest posts not already included. */
function mergeSimilarityAndRecency<T extends { similarity: number }>(
  rows: T[],
  totalLimit: number,
  keyFn: (row: T) => string,
  postedAtFn: (row: T) => number
): T[] {
  if (rows.length <= totalLimit) return rows.slice();
  const simShare = Math.max(1, Math.floor((totalLimit * 2) / 3));
  const recentShare = Math.max(1, totalLimit - simShare);
  const bySim = rows.slice().sort((a, b) => b.similarity - a.similarity);
  const byRecent = rows.slice().sort((a, b) => postedAtFn(b) - postedAtFn(a));
  const out: T[] = [];
  const seen = new Set<string>();
  for (const row of bySim) {
    if (out.length >= simShare) break;
    const key = keyFn(row);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(row);
  }
  for (const row of byRecent) {
    if (out.length >= simShare + recentShare) break;
    const key = keyFn(row);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(row);
  }
  // keep filling from similarity order if still short
  for (const row of bySim) {
    if (out.length >= totalLimit) break;
    const key = keyFn(row);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(row);
  }
  return out;
}

/** UI order: newest-first among top-similarity band, then remaining by similarity. */
function orderCommentsForUi(rows: CommentRow[]): CommentRow[] {
  if (rows.length <= 1) return rows.slice();
  const bySim = rows.slice().sort((a, b) => b.similarity - a.similarity);
  const head = bySim.slice(0, Math.min(40, bySim.length));
  const headRecent = head.slice().sort((a, b) => recencyScore(b) - recencyScore(a));
  const headKeys = new Set(headRecent.map(commentKey));
  const rest = bySim.filter((row) => !headKeys.has(commentKey(row)));
  return [...headRecent, ...rest];
}

async function embedQuery(query: string): Promise<number[]> {
  const apiKey = (Deno.env.get("GEMINI_API_KEY") || "").trim();
  if (!apiKey) throw new Error("Missing env: GEMINI_API_KEY");

  const response = await fetch(`${GEMINI_EMBED_URL}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: `models/${GEMINI_EMBED_MODEL}`,
      content: { parts: [{ text: query }] },
      taskType: "RETRIEVAL_QUERY",
      outputDimensionality: GEMINI_EMBED_DIM,
    }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Gemini embedding failed: HTTP ${response.status} ${text.slice(0, 240)}`);
  }
  const payload = await response.json();
  const values = payload?.embedding?.values;
  if (!Array.isArray(values) || values.length === 0) {
    throw new Error("Gemini embedding response is empty");
  }
  return values as number[];
}

function buildAnswerContext(
  comments: CommentRow[],
  chunks: ChunkRow[],
  sourcesById: Map<number, Record<string, unknown>>
): string {
  const parts: string[] = [];
  comments.forEach((row, index) => {
    const body = buildSnippet(row.content, ANSWER_SNIPPET_LIMIT);
    if (!body) return;
    parts.push(
      `[コミュニティ${index + 1}] id=${asString(row.comment_id)} author=${asString(row.author_name)} posted=${asString(row.posted_at)} similarity=${Number(row.similarity || 0).toFixed(3)}\n${body}`
    );
  });
  chunks.forEach((row, index) => {
    const body = buildSnippet(row.content, ANSWER_SNIPPET_LIMIT);
    if (!body) return;
    const sourceId = row.source_id != null ? Number(row.source_id) : null;
    const title =
      sourceId != null
        ? asString(sourcesById.get(sourceId)?.title) || asString(row.source_key)
        : asString(row.source_key);
    parts.push(
      `[セミナー${index + 1}] chunk=${asString(row.chunk_key)} title=${title || "（無題）"} start=${asString(row.start_sec)} similarity=${Number(row.similarity || 0).toFixed(3)}\n${body}`
    );
  });
  return parts.join("\n\n");
}

function buildAnswerPrompt(query: string, answerContext: string): string {
  return [
    "あなたは神・大家さん倶楽部の情報Q&Aアシスタントです。",
    "次の「参考情報テキスト」だけを根拠に、日本語でできるだけ網羅的に答えてください。推測で新しい事実を足さないこと。",
    "",
    "【重要ルール】",
    "1. 参考情報テキストが空でない場合、「参照内で確証が取れないため、お答えすることができません。」という一文だけの回答は禁止。",
    "2. 融資条件・購入事例・エリア事情・注意喚起・収支・修繕・契約など、質問テーマに関係する記述があれば、テーマごとに箇条書きで厚めに要約すること（完全一致の見出しは不要）。",
    "3. 参考内に新しい具体事例・金額・期間・実務Tipsがあれば優先して含めること（古い一般論だけで終わらせない）。",
    "4. 足りない点だけ『参照内では触れられていない』と補足してよい。",
    "5. 参考情報テキストが本当に空のときだけ、確証が取れない旨を書いてよい。",
    "6. 回答本文に出典一覧やコミュニティ／セミナーの列挙は書かない（画面UIが表示する）。",
    "",
    "参考情報テキスト:",
    answerContext,
    "",
    "質問:",
    query,
  ].join("\n");
}

async function summarizeAnswer(query: string, answerContext: string): Promise<string> {
  const trimmed = answerContext.trim();
  if (!trimmed) return REFUSAL;

  const apiKey = (Deno.env.get("GEMINI_API_KEY") || "").trim();
  if (!apiKey) throw new Error("Missing env: GEMINI_API_KEY");

  const response = await fetch(`${GEMINI_GENERATE_URL}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ role: "user", parts: [{ text: buildAnswerPrompt(query, trimmed) }] }],
      generationConfig: {
        temperature: 0.2,
        maxOutputTokens: 8192,
      },
    }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Gemini generate failed: HTTP ${response.status} ${text.slice(0, 240)}`);
  }
  const payload = await response.json();
  const text = asString(payload?.candidates?.[0]?.content?.parts?.[0]?.text).trim();
  if (!text) throw new Error("Gemini generate response is empty");

  if (text.includes("確証が取れない") && text.length < 80) {
    return [
      "参考情報から読み取れる留意点は次のとおりです。",
      "",
      trimmed
        .split("\n\n")
        .slice(0, 8)
        .map((block, i) => {
          const lines = block.split("\n");
          const body = lines.slice(1).join(" ").slice(0, 200);
          return `${i + 1}. ${body}`;
        })
        .join("\n"),
      "",
      "※詳細は下の関連コミュニティ投稿・関連セミナーも確認してください。",
    ].join("\n");
  }
  return text;
}

async function logSearchEvent(
  sb: ReturnType<typeof createClient>,
  payload: Record<string, unknown>
): Promise<void> {
  try {
    const { error } = await sb.from("app_qa_search_events").insert(payload);
    if (error) {
      console.error("app_qa_search_events insert failed", error.message);
    }
  } catch (err) {
    console.error("app_qa_search_events insert exception", err);
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders() });
  }
  if (req.method !== "POST") {
    return json({ errorMessage: "method_not_allowed" }, 405);
  }

  const body = (await req.json().catch(() => null)) as SemanticSearchRequest | null;
  if (!isAuthorized(req, body)) {
    return json({ errorMessage: "forbidden" }, 403);
  }

  const query = asString(body?.query).trim();
  if (!query) {
    return json({
      answer: REFUSAL,
      usedSources: '{"comment_ids":[],"chunk_keys":[]}',
      relatedComments: [],
      relatedChunks: [],
      relatedSources: [],
      answerContext: "",
      hitCount: 0,
    });
  }

  try {
    const commentLimit = Math.max(
      1,
      Math.min(MAX_COMMENT_LIMIT, Number(body?.comment_limit ?? DEFAULT_COMMENT_LIMIT))
    );
    const chunkLimit = Math.max(
      1,
      Math.min(MAX_CHUNK_LIMIT, Number(body?.chunk_limit ?? DEFAULT_CHUNK_LIMIT))
    );
    const matchThreshold = Number.isFinite(Number(body?.match_threshold))
      ? Number(body?.match_threshold)
      : DEFAULT_MATCH_THRESHOLD;
    const skipAnswer = body?.skip_answer === true;

    const embedding = await embedQuery(query);
    const supabaseUrl = (Deno.env.get("SUPABASE_URL") || "").trim();
    const serviceKey = (Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "").trim();
    if (!supabaseUrl || !serviceKey) {
      throw new Error("Missing env: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY");
    }
    const sb = createClient(supabaseUrl, serviceKey, {
      auth: { persistSession: false, autoRefreshToken: false },
    });

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

    const commentRows: CommentRow[] = (commentsRpc.data || []).map((row: Record<string, unknown>) => ({
      source_type: asString(row.source_type) || null,
      comment_id: asString(row.comment_id) || null,
      posted_at: asString(row.posted_at) || null,
      author_name: asString(row.author_name) || null,
      content: buildSnippet(row.content),
      similarity: Number(row.similarity || 0),
    }));

    const chunkRowsRaw: ChunkRow[] = (chunksRpc.data || []).map((row: Record<string, unknown>) => ({
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
        chunkRowsRaw
          .map((row) => row.source_id)
          .filter((value): value is number => typeof value === "number")
      )
    );

    let relatedSources: Array<Record<string, unknown>> = [];
    if (sourceIds.length > 0) {
      const { data: sources, error } = await sb
        .from("knowledge_sources")
        .select("id,source_key,title,video_url,origin_path,content_channel")
        .in("id", sourceIds);
      if (error) throw new Error(`knowledge_sources fetch failed: ${error.message}`);
      relatedSources = (sources || []).map((row: Record<string, unknown>) => ({
        id: Number(row.id),
        source_key: asString(row.source_key),
        title: asString(row.title),
        video_url: asString(row.video_url) || null,
        origin_path: asString(row.origin_path) || null,
        content_channel: asString(row.content_channel) || null,
      }));
    }

    const sourceById = new Map<number, Record<string, unknown>>();
    for (const source of relatedSources) {
      sourceById.set(Number(source.id), source);
    }

    const relatedChunks: ChunkRow[] = chunkRowsRaw.map((row) => ({
      ...row,
      source_key:
        row.source_id != null
          ? asString(sourceById.get(row.source_id)?.source_key) || null
          : null,
    }));

    const commentsForAnswer = mergeSimilarityAndRecency(
      commentRows,
      Math.min(ANSWER_COMMENT_LIMIT, commentRows.length),
      commentKey,
      recencyScore
    );
    const chunksForAnswer = relatedChunks
      .slice()
      .sort((a, b) => b.similarity - a.similarity)
      .slice(0, Math.min(ANSWER_CHUNK_LIMIT, relatedChunks.length));

    const answerContext = buildAnswerContext(commentsForAnswer, chunksForAnswer, sourceById);
    const answer = skipAnswer ? "" : await summarizeAnswer(query, answerContext);

    const usedSources = JSON.stringify({
      comment_ids: commentsForAnswer.map((row) => asString(row.comment_id)).filter(Boolean),
      chunk_keys: chunksForAnswer.map((row) => asString(row.chunk_key)).filter(Boolean),
    });

    const commentsForUi = orderCommentsForUi(commentRows);
    const relatedCommentsForClient = commentsForUi.map((row) => ({
      ...row,
      content: buildSnippet(row.content, 240),
    }));
    const relatedChunksForClient = relatedChunks.map((row) => ({
      ...row,
      content: buildSnippet(row.content, 240),
    }));

    // Phase 13: analytics event (best-effort)
    await logSearchEvent(sb, {
      search_mode: "semantic",
      query_text: query.slice(0, 2000),
      session_id: asString(body?.session_id) || null,
      user_id: asString(body?.user_id) || null,
      comment_hit_count: commentRows.length,
      chunk_hit_count: relatedChunks.length,
      answer_comment_count: commentsForAnswer.length,
      answer_chunk_count: chunksForAnswer.length,
      match_threshold: matchThreshold,
      used_sources: usedSources,
    });

    return json({
      answer,
      usedSources,
      relatedComments: relatedCommentsForClient,
      relatedChunks: relatedChunksForClient,
      relatedSources,
      hitCount: commentRows.length + relatedChunks.length,
      meta: {
        commentHitCount: commentRows.length,
        chunkHitCount: relatedChunks.length,
        answerCommentCount: commentsForAnswer.length,
        answerChunkCount: chunksForAnswer.length,
        matchThreshold,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "semantic_search_failed";
    return json({ errorMessage: message }, 500);
  }
});
