import {labelAnswerSources,attachReferenceLabels,mentionedSourceLabels} from '../../../lib/searchReferences.ts';
import {createQueryEmbeddingCache,embeddingKey} from '../../../lib/queryEmbeddingCache.ts';
// Supabase Edge Function: semantic search + answer summary.
// Auth: X-Semantic-Shared-Secret (or body.secret). Deploy with --no-verify-jwt.
//
// Thoroughness over speed: recall at least as many hits as normal search (100/50),
// blend recent posts into answer context, allow longer summaries (within ~150s wall clock).

import { createClient, type SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const GEMINI_EMBED_MODEL = "gemini-embedding-001";
const GEMINI_ANSWER_MODEL = "gemini-3-flash-preview";
// (1) 使用量の削減: raimo-auth が answer_tier=lite を付けた質問だけ軽いモデル＋短い参考情報で答える。
// 軽いモデルが使えないとき（名前の変更・停止）は今のモデルに戻す。
const GEMINI_LITE_MODEL = (Deno.env.get("GEMINI_LITE_MODEL") || "gemini-2.5-flash-lite").trim();
const LITE_LIMITS = { comments: 30, chunks: 15, openchats: 10 };
const GEMINI_EMBED_DIM = 768;
const queryEmbeddingCache=createQueryEmbeddingCache(GEMINI_EMBED_DIM);
const GEMINI_EMBED_URL =
  `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_EMBED_MODEL}:embedContent`;
const GEMINI_GENERATE_URL =
  `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_ANSWER_MODEL}:generateContent`;
const SNIPPET_LIMIT = 800;
const ANSWER_SNIPPET_LIMIT = 600;
const DEFAULT_MATCH_THRESHOLD = 0.22;
const DEFAULT_COMMENT_LIMIT = 100;
const DEFAULT_CHUNK_LIMIT = 50;
const DEFAULT_OPENCHAT_LIMIT = 20;
const MAX_COMMENT_LIMIT = 150;
const MAX_CHUNK_LIMIT = 80;
const MAX_OPENCHAT_LIMIT = 50;
const ANSWER_COMMENT_LIMIT = 50;
const ANSWER_CHUNK_LIMIT = 25;
const ANSWER_OPENCHAT_LIMIT = 15;
const REFUSAL =
  "参照内で確証が取れないため、お答えすることができません。";

type SemanticSearchRequest = {
  query?: string;
  comment_limit?: number;
  chunk_limit?: number;
  openchat_limit?: number;
  match_threshold?: number;
  skip_answer?: boolean;
  answer_tier?: string;
  list_openchat?: boolean;
  only_attachments?: boolean;
  /** 「DBで見る」用: line_openchat_logs.id を正確に取得（query の KW 検索ではヒットしない） */
  openchat_id?: string;
  chat_title?: string;
  secret?: string;
  session_id?: string;
  user_id?: string;
  /** 同じチャットの直前のやり取り（古い順）。スイッチ chat_context の人だけ、サーバーが付ける（2026-11-11）。 */
  history?: unknown;
  /** 調べる前にAIが質問を言い直す／意図が読めなければ聞き返す（スイッチ chat_context の人だけ、2026-11-11）。 */
  clarify?: boolean;
};

export type ChatTurn = { question: string; answer: string };

// 直前のやり取りは最大3往復・質問500字・回答1500字まで（プロンプトの膨張を防ぐ）。
export function normalizeHistory(value: unknown): ChatTurn[] {
  if (!Array.isArray(value)) return [];
  return value.map((t) => ({
    question: asString((t as Record<string, unknown>)?.question).trim().slice(0, 500),
    answer: asString((t as Record<string, unknown>)?.answer).trim().slice(0, 1500),
  })).filter((t) => t.question).slice(-3);
}

// 検索（意味検索のベクトル）に使う文。「また詳しく」のような短い続きの質問でも、前の質問のテーマで探す。
export function contextualSearchQuery(query: string, history: ChatTurn[]): string {
  if (!history.length) return query;
  return [...history.map((t) => t.question), query].join("\n").slice(-1200);
}

// 聞き返しの答えの目印。次の質問では続けて聞き返さない（聞き返しは続けて1回まで）。
export const CLARIFY_MARK = "【確認】";

export type QueryPlan = { action: "search" | "ask"; searchQuery: string; ask: string; options: string[] };

export function buildPlanPrompt(query: string, history: ChatTurn[], allowAsk: boolean): string {
  return [
    "あなたは神・大家さん倶楽部（不動産投資の会員コミュニティ）のQ&A検索の前処理係です。",
    "会員の今回の質問を、検索に使う1文の質問に言い直してください。答えそのものは書かないこと。",
    "",
    "【ルール】",
    "1. 「それ」「法人での事例」「もっと詳しく」のように対象が省略されていたら、これまでのやり取りから補って、単独で意味が通る質問にする（例: 前がバックファイナンスの話なら「法人でのバックファイナンスの事例」）。",
    "2. 今回の質問が前と別の話題なら、前の話題を混ぜない。",
    allowAsk
      ? "3. やり取りを読んでも何について知りたいのかが本当に決められないとき（候補が2つ以上あり、どれかで答えが大きく変わるとき）だけ action を ask にし、短い確認の質問と、選べる候補を2〜4個つける。少しでも推測できるなら ask にせず search にする。"
      : "3. 今回は聞き返さない。必ず action を search にする。",
    "4. 次のJSONだけを返す: {\"action\":\"search\"または\"ask\",\"search_query\":\"言い直した質問\",\"ask\":\"確認の質問（askのときだけ）\",\"options\":[\"候補1\",\"候補2\"]}",
    "",
    "【これまでのやり取り（古い順）】",
    ...(history.length ? history.flatMap((t, i) => [`(${i + 1}) 質問: ${t.question}`, `(${i + 1}) 回答の冒頭: ${t.answer.slice(0, 300) || "（記録なし）"}`]) : ["（なし。これが最初の質問）"]),
    "",
    "【今回の質問】",
    query,
  ].join("\n");
}

export function parsePlan(text: string, query: string, allowAsk: boolean): QueryPlan | null {
  let raw: Record<string, unknown>;
  try { raw = JSON.parse(String(text || "").replace(/^```(?:json)?\s*|\s*```$/g, "")); } catch { return null; }
  if (!raw || typeof raw !== "object") return null;
  const searchQuery = asString(raw.search_query).trim().slice(0, 300) || query;
  const ask = asString(raw.ask).trim().slice(0, 300);
  const options = (Array.isArray(raw.options) ? raw.options : []).map((o) => asString(o).trim().slice(0, 100)).filter(Boolean).slice(0, 4);
  if (allowAsk && raw.action === "ask" && ask) return { action: "ask", searchQuery, ask, options };
  return { action: "search", searchQuery, ask: "", options: [] };
}

export function clarificationAnswer(plan: QueryPlan): string {
  return [
    `${CLARIFY_MARK}${plan.ask}`,
    ...(plan.options.length ? ["", ...plan.options.map((o, i) => `${i + 1}. ${o}`), "", "番号か言葉でお知らせください。続けて調べます。"] : ["", "お知らせいただければ、続けて調べます。"]),
  ].join("\n");
}

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

type OpenchatRow = {
  id: string;
  route_id: string | null;
  chat_title: string | null;
  chat_name: string | null;
  stream_type: string | null;
  thread_title: string | null;
  posted_at: string | null;
  post_date: string | null;
  sender_name: string | null;
  content: string;
  similarity: number;
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

/** sync が付与する id（例: oc_df0b7a57e622c765a1c39c6e）かどうかを判定 */
function looksLikeOpenchatId(value: string): boolean {
  return /^oc_[0-9a-f]{16,64}$/i.test(value.trim());
}

const OPENCHAT_LIST_SELECT =
  "id,route_id,chat_title,chat_name,stream_type,thread_title,posted_at,post_date,sender_name,content";

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
  if (!expected) return false;
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

async function embedQuery(query: string, signal?: AbortSignal): Promise<number[]> {
  const apiKey = (Deno.env.get("GEMINI_API_KEY") || "").trim();
  if (!apiKey) throw new Error("Missing env: GEMINI_API_KEY");

  const response = await fetch(`${GEMINI_EMBED_URL}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    signal,
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
    throw new Error(`gemini_embedding_http_${response.status}`);
  }
  const payload = await response.json();
  const values = payload?.embedding?.values;
  if (!Array.isArray(values) || values.length === 0) {
    throw new Error("Gemini embedding response is empty");
  }
  return values as number[];
}

/** 秒 → mm:ss（回答本文で「12:34頃」と書けるようにする） */
function formatMmSs(value: number | null): string {
  const total = Math.max(0, Math.floor(Number(value) || 0));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** 取込経路の識別ラベル（例: 【Vimeo自動字幕・暫定】）は回答に出さない */
function displaySourceTitle(title: string): string {
  // 「（動画1106455203）」は取込時の Vimeo 番号。回答に写らないよう AI に渡す題名から外す（11/11 松野さん）
  return title.replace(/^\s*【[^】]*(?:暫定|自動字幕)[^】]*】\s*/, "").replace(/\s*[（(]動画\s*[0-9０-９]+[）)]/g, "").trim();
}

function buildAnswerContext(
  comments: CommentRow[],
  chunks: ChunkRow[],
  sourcesById: Map<number, Record<string, unknown>>,
  openchats: OpenchatRow[] = []
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
    const title = displaySourceTitle(
      sourceId != null
        ? asString(sourcesById.get(sourceId)?.title) || asString(row.source_key)
        : asString(row.source_key)
    );
    const range =
      row.end_sec != null && row.end_sec > (row.start_sec ?? 0)
        ? `${formatMmSs(row.start_sec)}〜${formatMmSs(row.end_sec)}`
        : formatMmSs(row.start_sec);
    parts.push(
      `[セミナー${index + 1}] chunk=${asString(row.chunk_key)} title=${title || "（無題）"} time=${range} similarity=${Number(row.similarity || 0).toFixed(3)}\n${body}`
    );
  });
  openchats.forEach((row, index) => {
    const body = buildSnippet(row.content, ANSWER_SNIPPET_LIMIT);
    if (!body) return;
    const when = asString(row.posted_at) || asString(row.post_date);
    parts.push(
      `[LINEオプチャ${index + 1}] id=${asString(row.id)} chat=${asString(row.chat_title) || asString(row.chat_name)} stream=${asString(row.stream_type)} thread=${asString(row.thread_title)} sender=${asString(row.sender_name)} posted=${when} similarity=${Number(row.similarity || 0).toFixed(3)}\n${body}`
    );
  });
  return parts.join("\n\n");
}

export function buildAnswerPrompt(query: string, answerContext: string, history: ChatTurn[] = [], rewritten = ""): string {
  const followUp = history.length ? [
    "",
    "【このチャットのこれまでのやり取り（古い順）】",
    ...history.flatMap((t, i) => [`(${i + 1}) 質問: ${t.question}`, `(${i + 1}) 回答の要旨: ${t.answer || "（記録なし）"}`]),
    "",
    "【続きの質問の扱い】",
    "A. 今回の質問は上のやり取りの続きです。「もっと詳しく」「また調べて」「それについて」のように対象が省略されていれば、直前の質問のテーマについて答えること。関係の薄い話題まで広げて網羅しない。",
    "B. 前の回答と同じ内容の繰り返しは短くし、前の回答で足りなかった点・より具体的な事例・数値・手順・新しい根拠を中心に深掘りすること。",
    "C. 今回の質問がはっきり別の話題なら、その話題として答えてよい。",
  ] : [];
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
    "6. 回答本文の末尾に出典一覧やコミュニティ／セミナーの列挙は書かない（画面UIが表示する）。",
    "7. セミナー動画（[セミナーN]）の内容を使った文には、その文末に（動画タイトル 12:34頃）の形で、該当する time の開始時刻を添える。どの動画の何分何秒あたりで何を話しているかが分かるようにすること。",
    "9. 根拠の番号は参考情報の[コミュニティN]、[セミナーN]、[LINEオプチャN]をそのまま使い、番号を振り直さない。「LINEオプチャ1、LINEオプチャ4」のように接頭辞を省略しない。動画を使った文は（セミナーN：動画タイトル 分:秒頃）の形で示す。",
    "10. 【LINE添付・内容未解析】はファイル名と投稿文だけの情報です。ファイル内部を読んだと扱わず、内容や数値を推測しないこと。関連資料として紹介する場合も元の[LINEオプチャN]を示すこと。",
    "8. セミナー動画の本文は自動文字起こしのため誤変換や句読点の欠落がある（例: 神王さんクラブ→神・大家さん倶楽部）。文脈から明らかな語は正しい表記に直して要約し、聞き取れない数値や固有名詞は断定しない。",
    "",
    ...followUp,
    "",
    "参考情報テキスト:",
    answerContext,
    "",
    "質問:",
    query,
    ...(rewritten && rewritten !== query ? ["", "（省略を補った質問: " + rewritten + "）"] : []),
  ].join("\n");
}

/** 実測用: Gemini 応答の usageMetadata を記録する入れ物（app_qa_search_events に保存） */
type GeminiUsage = {
  model: string;
  prompt_tokens: number;
  output_tokens: number;
  thought_tokens: number;
  calls: number;
};

function newGeminiUsage(): GeminiUsage {
  return { model: GEMINI_ANSWER_MODEL, prompt_tokens: 0, output_tokens: 0, thought_tokens: 0, calls: 0 };
}

function addUsageMetadata(usage: GeminiUsage | undefined, meta: unknown): void {
  if (!usage || !meta || typeof meta !== "object") return;
  const m = meta as Record<string, unknown>;
  const n = (v: unknown) => (Number.isFinite(Number(v)) ? Math.max(0, Math.floor(Number(v))) : 0);
  usage.prompt_tokens += n(m.promptTokenCount);
  usage.output_tokens += n(m.candidatesTokenCount);
  usage.thought_tokens += n(m.thoughtsTokenCount);
  usage.calls += 1;
}

async function summarizeAnswer(
  query: string,
  answerContext: string,
  usage?: GeminiUsage,
  signal?: AbortSignal,
  lite = false,
  history: ChatTurn[] = [],
  rewritten = ""
): Promise<string> {
  const trimmed = answerContext.trim();
  if (!trimmed) return REFUSAL;

  const apiKey = (Deno.env.get("GEMINI_API_KEY") || "").trim();
  if (!apiKey) throw new Error("Missing env: GEMINI_API_KEY");

  const call = (url: string) => fetch(`${url}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ role: "user", parts: [{ text: buildAnswerPrompt(query, trimmed, history, rewritten) }] }],
      generationConfig: {
        temperature: 0.2,
        maxOutputTokens: 8192,
      },
    }),
  });
  let response: Response | null = null;
  if (lite && /^[a-z0-9.\-]{3,60}$/.test(GEMINI_LITE_MODEL)) {
    response = await call(`https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_LITE_MODEL}:generateContent`);
    if (response.ok) { if (usage) usage.model = GEMINI_LITE_MODEL; }
    else { await response.text().catch(() => ""); response = null; }
  }
  if (!response) response = await call(GEMINI_GENERATE_URL);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`gemini_generation_http_${response.status}`);
  }
  const payload = await response.json();
  addUsageMetadata(usage, payload?.usageMetadata);
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
      "※詳細は下の関連コミュニティ投稿・関連セミナー・関連LINEオプチャも確認してください。",
    ].join("\n");
  }
  return text;
}

// 調べる前の言い直し・聞き返し。軽いモデルで1回だけ。失敗したら null（今までどおりの検索に戻す）。
async function planQuery(query: string, history: ChatTurn[], usage: GeminiUsage, signal?: AbortSignal): Promise<QueryPlan | null> {
  const apiKey = (Deno.env.get("GEMINI_API_KEY") || "").trim();
  if (!apiKey) return null;
  const allowAsk = !(history.length && history[history.length - 1].answer.startsWith(CLARIFY_MARK));
  const model = /^[a-z0-9.\-]{3,60}$/.test(GEMINI_LITE_MODEL) ? GEMINI_LITE_MODEL : GEMINI_ANSWER_MODEL;
  try {
    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(apiKey)}`, {
      method: "POST", signal, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: buildPlanPrompt(query, history, allowAsk) }] }],
        generationConfig: { temperature: 0, maxOutputTokens: 512, responseMimeType: "application/json" },
      }),
    });
    if (!response.ok) { await response.text().catch(() => ""); return null; }
    const payload = await response.json();
    addUsageMetadata(usage, payload?.usageMetadata);
    return parsePlan(asString(payload?.candidates?.[0]?.content?.parts?.[0]?.text), query, allowAsk);
  } catch (error) {
    if (signal?.aborted) throw error;
    return null;
  }
}

function mapOpenchatRow(row: Record<string, unknown>): OpenchatRow {
  return {
    id: asString(row.id),
    route_id: asString(row.route_id) || null,
    chat_title: asString(row.chat_title) || null,
    chat_name: asString(row.chat_name) || null,
    stream_type: asString(row.stream_type) || null,
    thread_title: asString(row.thread_title) || null,
    posted_at: asString(row.posted_at) || null,
    post_date: asString(row.post_date) || null,
    sender_name: asString(row.sender_name) || null,
    content: buildSnippet(row.content),
    similarity: Number(row.similarity || 0),
  };
}

async function fetchOpenchatHits(
  // deno-lint-ignore no-explicit-any
  sb: any,
  keywordResult: PromiseLike<{data: unknown;error: unknown}>,
  embedding: number[],
  matchThreshold: number,
  openchatLimit: number
): Promise<OpenchatRow[]> {
  const [semRpc, kwRpc] = await Promise.all([
    sb.rpc("match_openchat_semantic", {
      query_embedding: embedding,
      match_threshold: matchThreshold,
      match_count: openchatLimit,
    }),
    keywordResult,
  ]);

  // A failed source is not an empty source. Do not spend a generation call on
  // silently incomplete evidence or present it as a complete search result.
  if(semRpc.error)throw new Error('match_openchat_semantic failed');
  if(kwRpc.error)throw new Error('search_openchat_keyword failed');

  const byId = new Map<string, OpenchatRow>();
  for (const row of (semRpc.data || []) as Record<string, unknown>[]) {
    const mapped = mapOpenchatRow(row);
    if (mapped.id) byId.set(mapped.id, mapped);
  }
  for (const row of (kwRpc.data || []) as Record<string, unknown>[]) {
    const mapped = mapOpenchatRow(row);
    if (!mapped.id) continue;
    const prev = byId.get(mapped.id);
    if (!prev || mapped.similarity > prev.similarity) {
      byId.set(mapped.id, mapped);
    }
  }
  return Array.from(byId.values())
    .sort((a, b) => b.similarity - a.similarity)
    .slice(0, openchatLimit);
}

/** 実トークンを列に展開。要約を呼んでいなければ null（未計測と区別する） */
function usageColumns(usage: GeminiUsage): Record<string, unknown> {
  if (usage.calls === 0) return {};
  return {
    gemini_model: usage.model,
    gemini_prompt_tokens: usage.prompt_tokens,
    gemini_output_tokens: usage.output_tokens,
    gemini_thought_tokens: usage.thought_tokens,
    gemini_calls: usage.calls,
  };
}

async function logSearchEvent(
  sb: SupabaseClient<any>,
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

export async function handleSemanticSearch(req: Request): Promise<Response> {
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
  const listOpenchat = body?.list_openchat === true;
  const history = normalizeHistory(body?.history);
  const searchQuery = contextualSearchQuery(query, history);

  if (!query && !listOpenchat) {
    return json({
      answer: REFUSAL,
      usedSources: '{"comment_ids":[],"chunk_keys":[],"openchat_ids":[]}',
      relatedComments: [],
      relatedChunks: [],
      relatedSources: [],
      relatedOpenchat: [],
      answerContext: "",
      hitCount: 0,
    });
  }

  const supabaseUrl = (Deno.env.get("SUPABASE_URL") || "").trim();
  const serviceKey = (Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "").trim();
  if (!supabaseUrl || !serviceKey) {
    return json({ errorMessage: "Missing env: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY" }, 500);
  }
  const sb = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
    global:{fetch:(input,init)=>fetch(input,{...init,signal:req.signal})},
  });

  const sessionId = asString(body?.session_id) || null;
  const userId = asString(body?.user_id) || null;
  const baseEvent = {
    search_mode: listOpenchat ? "openchat_list" : "semantic",
    query_text: (query || asString(body?.chat_title)).slice(0, 2000),
    session_id: sessionId,
    user_id: userId,
  };

  // Phase 14-1: emergency kill switch (no redeploy needed)
  if ((Deno.env.get("SEMANTIC_SEARCH_DISABLED") || "").trim() === "1" && !listOpenchat) {
    await logSearchEvent(sb, {
      ...baseEvent,
      result_status: "disabled",
      error_message: "SEMANTIC_SEARCH_DISABLED=1",
    });
    return json(
      {
        errorMessage:
          "意味検索は一時停止中です。通常検索（意味検索モードOFF）をご利用ください",
        code: "semantic_disabled",
      },
      503
    );
  }

  const geminiUsage = newGeminiUsage();
  let embeddingProviderCalls=0;
  try {
    const openchatLimit = Math.max(
      1,
      Math.min(MAX_OPENCHAT_LIMIT, Number(body?.openchat_limit ?? DEFAULT_OPENCHAT_LIMIT))
    );

    // 一覧／KW ブラウズ（意味検索タブ用・シークレット必須は isAuthorized 済み）
    if (listOpenchat) {
      const openchatId =
        asString(body?.openchat_id).trim() ||
        (looksLikeOpenchatId(query) ? query.trim() : "");

      // 「DBで見る」: id は本文 KW に出ないため、eq で1件取得する
      if (openchatId) {
        const { data, error } = await sb
          .from("line_openchat_logs")
          .select(OPENCHAT_LIST_SELECT)
          .eq("ingest_status", "ready")
          .eq("id", openchatId)
          .limit(1);
        if (error) throw new Error(`openchat by id failed: ${error.message}`);
        const relatedOpenchat = ((data || []) as Record<string, unknown>[]).map((row) =>
          mapOpenchatRow({ ...row, similarity: 0 })
        );
        await logSearchEvent(sb, {
          ...baseEvent,
          query_text: openchatId.slice(0, 2000),
          comment_hit_count: 0,
          chunk_hit_count: 0,
          result_status: "ok",
          used_sources: JSON.stringify({ openchat_ids: relatedOpenchat.map((r) => r.id) }),
        });
        return json({
          relatedOpenchat,
          hitCount: relatedOpenchat.length,
          meta: {
            openchatHitCount: relatedOpenchat.length,
            mode: "by_id",
            openchatId,
          },
        });
      }

      let q = sb
        .from("line_openchat_logs")
        .select(OPENCHAT_LIST_SELECT)
        .eq("ingest_status", "ready")
        .order("posted_at", { ascending: false, nullsFirst: false })
        .limit(Math.min(200, openchatLimit * 5));
      const titleFilter = asString(body?.chat_title).trim();
      if (body?.only_attachments === true) q = q.eq("source_system", "line_openchat_attachment");
      if (titleFilter) {
        q = q.ilike("chat_title", `%${titleFilter}%`);
      }
      if (query) {
        const literal=query.replace(/\\/g,"\\\\").replace(/"/g,'\\"');
        // id.eq も併用（oc_ 以外の旧 id や手貼り対策）
        q = q.or(
          `id.eq."${literal}",content.ilike."%${literal}%",chat_title.ilike."%${literal}%",sender_name.ilike."%${literal}%",thread_title.ilike."%${literal}%"`
        );
      }
      const { data, error } = await q;
      if (error) throw new Error(`openchat list failed: ${error.message}`);
      const relatedOpenchat = ((data || []) as Record<string, unknown>[]).map((row) =>
        mapOpenchatRow({ ...row, similarity: 0 })
      );
      await logSearchEvent(sb, {
        ...baseEvent,
        comment_hit_count: 0,
        chunk_hit_count: 0,
        result_status: "ok",
        used_sources: JSON.stringify({ openchat_ids: relatedOpenchat.map((r) => r.id) }),
      });
      return json({
        relatedOpenchat,
        hitCount: relatedOpenchat.length,
        meta: { openchatHitCount: relatedOpenchat.length, mode: "list" },
      });
    }

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
    const liteAnswer = body?.answer_tier === "lite";

    // 調べる前に、省略を補った質問に言い直す。意図が読めなければ調べずに聞き返す（chat_context の人だけ）。
    let plan: QueryPlan | null = null;
    if (body?.clarify === true && !skipAnswer) {
      plan = await planQuery(query, history, geminiUsage, req.signal);
      if (plan?.action === "ask") {
        const answer = clarificationAnswer(plan);
        await logSearchEvent(sb, { ...baseEvent, comment_hit_count: 0, chunk_hit_count: 0, result_status: "ok",
          used_sources: '{"comment_ids":[],"chunk_keys":[],"openchat_ids":[]}', ...usageColumns(geminiUsage), meta: { clarification: true } });
        return json({ answer, clarification: true, usedSources: '{"comment_ids":[],"chunk_keys":[],"openchat_ids":[]}',
          relatedComments: [], relatedChunks: [], relatedSources: [], relatedOpenchat: [], referenceLabels: {}, referenceSelection: "provided-context",
          answerModel: geminiUsage.calls > 0 ? geminiUsage.model : "", hitCount: 0 });
      }
    }
    const vectorQuery = plan ? plan.searchQuery : searchQuery;

    // Keyword retrieval does not depend on the vector. Start it immediately,
    // while retaining its rejection for the eventual join (including embed failure).
    const retrievalStarted=performance.now();
    const keywordResult=Promise.resolve(sb.rpc("search_openchat_keyword", {
      query_text: (plan ? plan.searchQuery : query).slice(0, 80), match_count: openchatLimit,
    }));
    void keywordResult.catch(()=>{});
    const embeddingStarted=performance.now();
    const cached=await queryEmbeddingCache.get(await embeddingKey(GEMINI_EMBED_MODEL,'RETRIEVAL_QUERY',GEMINI_EMBED_DIM,vectorQuery),
      signal=>{embeddingProviderCalls++;return embedQuery(vectorQuery,signal);},req.signal);
    const embedding=cached.values;
    const embeddingMs=Math.round(performance.now()-embeddingStarted);

    // Only the chunk result is needed to resolve video titles/URLs. Do not
    // serialize that read behind unrelated comment or LINE queries.
    const chunkPipeline=(async()=>{
      const chunksRpc=await sb.rpc("match_chunks_semantic", {
        query_embedding: embedding, match_threshold: matchThreshold, match_count: chunkLimit,
      });
      if(chunksRpc.error)throw new Error(`match_chunks_semantic failed: ${chunksRpc.error.message}`);
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

      return {chunkRowsRaw,relatedSources};
    })();
    const [commentsRpc, chunkData, openchatRows] = await Promise.all([
      sb.rpc("match_comments_semantic", {
        query_embedding: embedding, match_threshold: matchThreshold, match_count: commentLimit,
      }),
      chunkPipeline,
      fetchOpenchatHits(sb, keywordResult, embedding, matchThreshold, openchatLimit),
    ]);
    if(commentsRpc.error)throw new Error(`match_comments_semantic failed: ${commentsRpc.error.message}`);
    const commentRows: CommentRow[] = (commentsRpc.data || []).map((row: Record<string, unknown>) => ({
      source_type: asString(row.source_type) || null,
      comment_id: asString(row.comment_id) || null,
      posted_at: asString(row.posted_at) || null,
      author_name: asString(row.author_name) || null,
      content: buildSnippet(row.content),
      similarity: Number(row.similarity || 0),
    }));
    const {chunkRowsRaw,relatedSources}=chunkData;

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

    const openchatsForAnswer = openchatRows
      .slice()
      .sort((a, b) => b.similarity - a.similarity)
      .slice(0, Math.min(liteAnswer ? LITE_LIMITS.openchats : ANSWER_OPENCHAT_LIMIT, openchatRows.length));

    const commentsForAnswer = mergeSimilarityAndRecency(
      commentRows,
      Math.min(liteAnswer ? LITE_LIMITS.comments : ANSWER_COMMENT_LIMIT, commentRows.length),
      commentKey,
      recencyScore
    );
    const chunksForAnswer = relatedChunks
      .slice()
      .sort((a, b) => b.similarity - a.similarity)
      .slice(0, Math.min(liteAnswer ? LITE_LIMITS.chunks : ANSWER_CHUNK_LIMIT, relatedChunks.length));

    const answerContext = buildAnswerContext(
      commentsForAnswer,
      chunksForAnswer,
      sourceById,
      openchatsForAnswer
    );
    const retrievalMs=Math.round(performance.now()-retrievalStarted);
    const answer = skipAnswer ? "" : await summarizeAnswer(query, answerContext, geminiUsage, req.signal, liteAnswer, history, plan ? plan.searchQuery : "");

    const referenceLabels=labelAnswerSources(commentsForAnswer,chunksForAnswer,openchatsForAnswer);
    const knownLabels=new Set([...Object.values(referenceLabels.comments),...Object.values(referenceLabels.chunks),...Object.values(referenceLabels.openchats)]);
    const mentioned=mentionedSourceLabels(answer,knownLabels);
    chunksForAnswer.forEach(row=>{
      const title=displaySourceTitle(asString(sourceById.get(Number(row.source_id))?.title));
      if(title && answer.includes(title) && answer.includes(formatMmSs(row.start_sec)))mentioned.add(referenceLabels.chunks[row.chunk_key]);
    });
    const hasMentioned=mentioned.size>0;
    const usedSources = JSON.stringify({
      comment_ids: commentsForAnswer.filter(row=>!hasMentioned||mentioned.has(referenceLabels.comments[asString(row.comment_id)])).map((row) => asString(row.comment_id)).filter(Boolean),
      chunk_keys: chunksForAnswer.filter(row=>!hasMentioned||mentioned.has(referenceLabels.chunks[asString(row.chunk_key)])).map((row) => asString(row.chunk_key)).filter(Boolean),
      openchat_ids: openchatsForAnswer.filter(row=>!hasMentioned||mentioned.has(referenceLabels.openchats[asString(row.id)])).map((row) => asString(row.id)).filter(Boolean),
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
    const relatedOpenchatForClient = openchatRows.map((row) => ({
      ...row,
      content: buildSnippet(row.content, 240),
    }));

    await logSearchEvent(sb, {
      ...baseEvent,
      comment_hit_count: commentRows.length,
      chunk_hit_count: relatedChunks.length,
      answer_comment_count: commentsForAnswer.length,
      answer_chunk_count: chunksForAnswer.length,
      match_threshold: matchThreshold,
      used_sources: usedSources,
      result_status: "ok",
      ...usageColumns(geminiUsage),
      meta:{...(plan?{rewritten_query:plan.searchQuery}:{}),embedding_cache_hit:cached.cacheHit,embedding_ms:embeddingMs,embedding_provider_calls:embeddingProviderCalls,retrieval_ms:retrievalMs},
    });

    return json({
      answer,
      usedSources,
      relatedComments: attachReferenceLabels(relatedCommentsForClient,"comment_id",referenceLabels.comments),
      relatedChunks: attachReferenceLabels(relatedChunksForClient,"chunk_key",referenceLabels.chunks),
      relatedSources,
      relatedOpenchat: attachReferenceLabels(relatedOpenchatForClient,"id",referenceLabels.openchats),
      referenceLabels,
      referenceSelection:hasMentioned?"mentioned":"provided-context",
      // (2) 評価と結び付けるため、実際に答えたモデルを返す（要約を呼ばなかったときは空）。11/11
      answerModel: geminiUsage.calls>0?geminiUsage.model:"",
      hitCount: commentRows.length + relatedChunks.length + openchatRows.length,
      meta: {
        embeddingProviderCalls,
        retrievalMs,
        embeddingCacheHit:cached.cacheHit,
        embeddingMs,
        commentHitCount: commentRows.length,
        chunkHitCount: relatedChunks.length,
        openchatHitCount: openchatRows.length,
        answerCommentCount: commentsForAnswer.length,
        answerChunkCount: chunksForAnswer.length,
        answerOpenchatCount: openchatsForAnswer.length,
        matchThreshold,
      },
    });
  } catch (error) {
    const original = error instanceof Error ? error.message : "semantic_search_failed";
    const message=/^gemini_(embedding|generation)_http_\d{3}$/.test(original)?original:(error instanceof Error?error.name:"semantic_search_failed");
    await logSearchEvent(sb, {
      ...baseEvent,
      result_status: "error",
      error_message: String(message).slice(0, 500),
      ...usageColumns(geminiUsage),
    });
    return json({ errorMessage: "意味検索を完了できませんでした。時間を置いて再試行してください。", code:"semantic_search_failed" }, 500);
  }
}
