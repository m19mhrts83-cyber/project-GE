/** kamiooya-qa からコメント／動画チャンクを検索し、ask 用ブロックを作る */

import { kamiooyaAdminOrNull } from "./client";

export type KamiooyaHit = {
  kind: "comment" | "chunk";
  title: string;
  snippet: string;
  meta?: string;
};

export type KamiooyaRetrieveResult = {
  ok: boolean;
  hits: KamiooyaHit[];
  promptBlock: string;
  notice: string;
  via: "semantic" | "keyword" | "unavailable" | "empty";
  error?: string;
};

function clip(s: string, n = 280): string {
  const t = s.replace(/\s+/g, " ").trim();
  return t.length <= n ? t : `${t.slice(0, n - 1)}…`;
}

async function embedQuery(query: string): Promise<number[] | null> {
  const apiKey = (process.env.GEMINI_API_KEY || "").trim();
  if (!apiKey) return null;
  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=` +
    encodeURIComponent(apiKey);
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "models/gemini-embedding-001",
      content: { parts: [{ text: query }] },
      taskType: "RETRIEVAL_QUERY",
      outputDimensionality: 768,
    }),
  });
  if (!res.ok) return null;
  const json = (await res.json()) as {
    embedding?: { values?: number[] };
  };
  const values = json.embedding?.values;
  return Array.isArray(values) && values.length ? values : null;
}

async function semanticRetrieve(
  query: string,
): Promise<{ hits: KamiooyaHit[]; error?: string } | null> {
  const sb = kamiooyaAdminOrNull();
  if (!sb) return null;
  const embedding = await embedQuery(query);
  if (!embedding) return null;

  const [commentsRpc, chunksRpc] = await Promise.all([
    sb.rpc("match_comments_semantic", {
      query_embedding: embedding,
      match_threshold: 0.5,
      match_count: 5,
    }),
    sb.rpc("match_chunks_semantic", {
      query_embedding: embedding,
      match_threshold: 0.5,
      match_count: 5,
    }),
  ]);

  if (commentsRpc.error && chunksRpc.error) {
    return {
      hits: [],
      error: commentsRpc.error.message || chunksRpc.error.message,
    };
  }

  const hits: KamiooyaHit[] = [];
  for (const row of (commentsRpc.data || []) as Record<string, unknown>[]) {
    hits.push({
      kind: "comment",
      title: String(row.author_name || row.source_type || "コメント"),
      snippet: clip(String(row.content || "")),
      meta: row.posted_at ? String(row.posted_at).slice(0, 10) : undefined,
    });
  }

  const chunkRows = (chunksRpc.data || []) as Record<string, unknown>[];
  const sourceIds = [
    ...new Set(
      chunkRows
        .map((r) => Number(r.source_id))
        .filter((n) => Number.isFinite(n)),
    ),
  ];
  const titleById = new Map<number, string>();
  if (sourceIds.length) {
    const { data: sources } = await sb
      .from("knowledge_sources")
      .select("id,title")
      .in("id", sourceIds);
    for (const s of sources || []) {
      titleById.set(Number((s as { id: number }).id), String((s as { title: string }).title));
    }
  }
  for (const row of chunkRows) {
    const sid = Number(row.source_id);
    const start = row.start_sec != null ? `${row.start_sec}s` : "";
    hits.push({
      kind: "chunk",
      title: titleById.get(sid) || String(row.chunk_key || "動画"),
      snippet: clip(String(row.content || "")),
      meta: [row.speaker, start].filter(Boolean).join(" · ") || undefined,
    });
  }
  return { hits };
}

async function keywordRetrieve(query: string): Promise<KamiooyaHit[]> {
  const sb = kamiooyaAdminOrNull();
  if (!sb) return [];
  const tokens = query
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2)
    .slice(0, 4);
  if (!tokens.length) return [];

  const hits: KamiooyaHit[] = [];
  // ilike OR を順に試す（PostgREST or フィルタ）
  const pattern = `%${tokens[0]}%`;
  const { data: comments } = await sb
    .from("comments")
    .select("author_name,source_type,content,posted_at")
    .ilike("content", pattern)
    .eq("is_deleted", false)
    .order("posted_at", { ascending: false })
    .limit(5);
  for (const row of comments || []) {
    hits.push({
      kind: "comment",
      title: String(
        (row as { author_name?: string }).author_name ||
          (row as { source_type?: string }).source_type ||
          "コメント",
      ),
      snippet: clip(String((row as { content?: string }).content || "")),
      meta: (row as { posted_at?: string }).posted_at
        ? String((row as { posted_at: string }).posted_at).slice(0, 10)
        : undefined,
    });
  }

  const { data: chunks } = await sb
    .from("knowledge_chunks")
    .select("chunk_key,content,speaker,start_sec,source_id,search_text")
    .ilike("search_text", pattern)
    .limit(5);
  const sourceIds = [
    ...new Set(
      (chunks || [])
        .map((r) => Number((r as { source_id?: number }).source_id))
        .filter((n) => Number.isFinite(n)),
    ),
  ];
  const titleById = new Map<number, string>();
  if (sourceIds.length) {
    const { data: sources } = await sb
      .from("knowledge_sources")
      .select("id,title")
      .in("id", sourceIds);
    for (const s of sources || []) {
      titleById.set(Number((s as { id: number }).id), String((s as { title: string }).title));
    }
  }
  for (const row of chunks || []) {
    const r = row as {
      source_id?: number;
      chunk_key?: string;
      content?: string;
      speaker?: string;
      start_sec?: number;
    };
    hits.push({
      kind: "chunk",
      title: titleById.get(Number(r.source_id)) || String(r.chunk_key || "動画"),
      snippet: clip(String(r.content || "")),
      meta: [r.speaker, r.start_sec != null ? `${r.start_sec}s` : ""]
        .filter(Boolean)
        .join(" · "),
    });
  }
  return hits;
}

function formatBlock(hits: KamiooyaHit[]): string {
  if (!hits.length) return "";
  const lines = ["【神大家ナレッジ根拠】（kamiooya-qa・読取のみ）"];
  hits.slice(0, 10).forEach((h, i) => {
    lines.push(
      `${i + 1}. [${h.kind === "comment" ? "コメント" : "動画"}] ${h.title}` +
        (h.meta ? ` (${h.meta})` : ""),
    );
    lines.push(`   ${h.snippet}`);
  });
  lines.push(
    "根拠に無いことは推測しない。タスク相談の参考として使う。",
  );
  return lines.join("\n");
}

/**
 * 質問文で kamiooya-qa を検索。未配線・失敗でも ok=false で止めない呼び出し側向け。
 */
export async function retrieveKamiooyaForAsk(
  query: string,
): Promise<KamiooyaRetrieveResult> {
  const q = query.trim();
  if (!q) {
    return {
      ok: false,
      hits: [],
      promptBlock: "",
      notice: "神大家DB: クエリが空のためスキップ",
      via: "empty",
    };
  }
  if (!kamiooyaAdminOrNull()) {
    return {
      ok: false,
      hits: [],
      promptBlock: "",
      notice:
        "神大家DB未配線（SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY）。聞く自体は続行",
      via: "unavailable",
    };
  }

  try {
    const sem = await semanticRetrieve(q);
    if (sem && sem.hits.length) {
      const comments = sem.hits.filter((h) => h.kind === "comment").length;
      const chunks = sem.hits.filter((h) => h.kind === "chunk").length;
      return {
        ok: true,
        hits: sem.hits,
        promptBlock: formatBlock(sem.hits),
        notice: `神大家DBから参照（意味検索）: コメント${comments}・動画${chunks}`,
        via: "semantic",
      };
    }
    if (sem?.error) {
      // fall through to keyword
    }
  } catch {
    /* keyword fallback */
  }

  try {
    const hits = await keywordRetrieve(q);
    if (hits.length) {
      const comments = hits.filter((h) => h.kind === "comment").length;
      const chunks = hits.filter((h) => h.kind === "chunk").length;
      return {
        ok: true,
        hits,
        promptBlock: formatBlock(hits),
        notice: `神大家DBから参照（キーワード）: コメント${comments}・動画${chunks}`,
        via: "keyword",
      };
    }
    return {
      ok: true,
      hits: [],
      promptBlock: "",
      notice: "神大家DBを検索したが該当なし",
      via: "empty",
    };
  } catch (e) {
    return {
      ok: false,
      hits: [],
      promptBlock: "",
      notice: `神大家DB検索失敗（聞くは続行）: ${e instanceof Error ? e.message : String(e)}`.slice(
        0,
        160,
      ),
      via: "unavailable",
      error: e instanceof Error ? e.message : String(e),
    };
  }
}
