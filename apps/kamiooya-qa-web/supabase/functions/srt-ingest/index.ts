// Admin SRT ingest → knowledge_sources / knowledge_chunks (+ optional embedding).
// Auth: X-Semantic-Shared-Secret. Deploy with --no-verify-jwt.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const GEMINI_EMBED_MODEL = "gemini-embedding-001";
const GEMINI_EMBED_DIM = 768;
const GEMINI_EMBED_URL =
  `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_EMBED_MODEL}:embedContent`;
const MAX_EMBED_CHUNKS = 40;
const MAX_SRT_CHARS = 1_500_000;

type Body = {
  secret?: string;
  title?: string;
  video_id?: string;
  video_url?: string;
  instructor?: string;
  srt_text?: string;
  skip_embed?: boolean;
};

type Cue = {
  start_sec: number;
  end_sec: number | null;
  speaker: string | null;
  text: string;
};

type Chunk = {
  start_sec: number;
  end_sec: number | null;
  speaker: string | null;
  content: string;
  content_hash: string;
  chunk_key: string;
  search_text: string;
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

function isAuthorized(req: Request, body: Body | null): boolean {
  const expected = (Deno.env.get("SEMANTIC_SEARCH_SHARED_SECRET") || "").trim();
  if (!expected) return true;
  const headerSecret = (req.headers.get("x-semantic-shared-secret") || "").trim();
  const bodySecret = asString(body?.secret).trim();
  return headerSecret === expected || bodySecret === expected;
}

async function sha1Hex16(text: string): Promise<string> {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-1", data);
  const hex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return hex.slice(0, 16);
}

function parseSrt(text: string): Cue[] {
  const blocks = text.replace(/^\uFEFF/, "").trim().split(/\n\s*\n/);
  const timeRe =
    /(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})/;
  const cues: Cue[] = [];
  for (const block of blocks) {
    let lines = block
      .split(/\r?\n/)
      .map((ln) => ln.replace(/^\uFEFF/, "").trim())
      .filter(Boolean);
    if (!lines.length) continue;
    if (/^\d+$/.test(lines[0]) && lines.length >= 2) lines = lines.slice(1);
    if (!lines.length) continue;
    const m = lines[0].match(timeRe);
    if (!m) continue;
    const start =
      Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
    const end =
      Number(m[5]) * 3600 + Number(m[6]) * 60 + Number(m[7]);
    const bodyLines = lines.slice(1);
    let speaker: string | null = null;
    const body: string[] = [];
    for (const bl of bodyLines) {
      if (bl.includes(":") && bl.split(":", 1)[0].length <= 20) {
        const idx = bl.indexOf(":");
        const sp = bl.slice(0, idx).trim();
        const rest = bl.slice(idx + 1).trim();
        if (rest && !/^\d+$/.test(sp)) {
          speaker = sp;
          body.push(rest);
          continue;
        }
      }
      body.push(bl);
    }
    const t = body.join(" ").trim();
    if (!t) continue;
    cues.push({ start_sec: start, end_sec: end, speaker, text: t });
  }
  return cues;
}

function chunkCues(
  cues: Cue[],
  maxSec = 40,
  maxChars = 600,
  overlapSec = 8,
): Array<{
  start_sec: number;
  end_sec: number | null;
  speaker: string | null;
  content: string;
}> {
  if (!cues.length) return [];
  const bodyOnly = cues.every((c) => c.start_sec === 0) && cues.length > 1;
  const chunks: Array<{
    start_sec: number;
    end_sec: number | null;
    speaker: string | null;
    content: string;
  }> = [];
  let buf: Cue[] = [];
  let bufStart = 0;
  let bufChars = 0;

  const flush = (nextOverlapFrom: number | null = null) => {
    if (!buf.length) return;
    const text = buf.map((c) => c.text).join(" ").trim();
    const speakers = buf.map((c) => c.speaker).filter(Boolean) as string[];
    chunks.push({
      start_sec: buf[0].start_sec,
      end_sec: buf[buf.length - 1].end_sec ?? buf[buf.length - 1].start_sec,
      speaker: speakers[0] || null,
      content: text,
    });
    if (nextOverlapFrom != null && !bodyOnly && overlapSec > 0) {
      buf = buf.filter((c) => c.start_sec >= nextOverlapFrom);
      bufChars = buf.reduce((n, c) => n + c.text.length, 0);
      bufStart = buf.length ? buf[0].start_sec : 0;
    } else {
      buf = [];
      bufChars = 0;
      bufStart = 0;
    }
  };

  for (const cue of cues) {
    if (!buf.length) {
      buf = [cue];
      bufStart = cue.start_sec;
      bufChars = cue.text.length;
      continue;
    }
    const span = cue.start_sec - bufStart;
    const wouldChars = bufChars + 1 + cue.text.length;
    if ((!bodyOnly && span >= maxSec) || wouldChars >= maxChars) {
      const overlapFrom = Math.max(0, cue.start_sec - overlapSec);
      flush(bodyOnly ? null : overlapFrom);
      if (!buf.length) {
        buf = [cue];
        bufStart = cue.start_sec;
        bufChars = cue.text.length;
      } else {
        buf.push(cue);
        bufChars += 1 + cue.text.length;
      }
    } else {
      buf.push(cue);
      bufChars = wouldChars;
    }
  }
  flush();
  return chunks;
}

async function buildChunks(videoId: string, cues: Cue[]): Promise<Chunk[]> {
  const raw = chunkCues(cues);
  const out: Chunk[] = [];
  for (const ch of raw) {
    const h = await sha1Hex16(ch.content);
    out.push({
      start_sec: ch.start_sec,
      end_sec: ch.end_sec,
      speaker: ch.speaker,
      content: ch.content,
      content_hash: h,
      chunk_key: `wv:${videoId}:${ch.start_sec}:${h}`,
      search_text: `${ch.speaker || ""} ${ch.content}`.trim(),
    });
  }
  return out;
}

async function embedDocument(text: string): Promise<number[]> {
  const apiKey = (Deno.env.get("GEMINI_API_KEY") || "").trim();
  if (!apiKey) throw new Error("Missing env: GEMINI_API_KEY");
  const response = await fetch(`${GEMINI_EMBED_URL}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: `models/${GEMINI_EMBED_MODEL}`,
      content: { parts: [{ text }] },
      taskType: "RETRIEVAL_DOCUMENT",
      outputDimensionality: GEMINI_EMBED_DIM,
    }),
  });
  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`embed HTTP ${response.status}: ${errText.slice(0, 200)}`);
  }
  const payload = await response.json();
  const values = payload?.embedding?.values;
  if (!Array.isArray(values) || !values.length) {
    throw new Error("empty embedding");
  }
  return values as number[];
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders() });
  }
  if (req.method !== "POST") {
    return json({ errorMessage: "method_not_allowed" }, 405);
  }

  const body = (await req.json().catch(() => null)) as Body | null;
  if (!isAuthorized(req, body)) {
    return json({ errorMessage: "forbidden" }, 403);
  }

  const title = asString(body?.title).trim();
  const videoId = asString(body?.video_id).trim();
  const videoUrl = asString(body?.video_url).trim();
  const instructor = asString(body?.instructor).trim();
  const srtText = asString(body?.srt_text);
  const skipEmbed = !!body?.skip_embed;

  if (!title || !videoId) {
    return json({ errorMessage: "title と video_id は必須です" }, 400);
  }
  if (!srtText.trim()) {
    return json({ errorMessage: "srt_text が空です" }, 400);
  }
  if (srtText.length > MAX_SRT_CHARS) {
    return json({ errorMessage: "SRT が大きすぎます（上限約1.5MB）" }, 400);
  }

  const cues = parseSrt(srtText);
  if (!cues.length) {
    return json({ errorMessage: "SRT から字幕キューを解析できませんでした" }, 400);
  }
  const chunks = await buildChunks(videoId, cues);
  if (!chunks.length) {
    return json({ errorMessage: "チャンクが0件です" }, 400);
  }

  const supabaseUrl = (Deno.env.get("SUPABASE_URL") || "").trim();
  const serviceKey = (Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "").trim();
  if (!supabaseUrl || !serviceKey) {
    return json({ errorMessage: "missing supabase env" }, 500);
  }
  const sb = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const sourceKey = `notta:${videoId}`;
  const sourcePayload = {
    source_key: sourceKey,
    source_kind: "video",
    content_channel: "seminar_video",
    title,
    video_id: videoId,
    video_url: videoUrl || null,
    instructor: instructor || null,
    origin_path: `admin-upload:${videoId}.srt`,
    meta_json: {
      ingest_via: "srt-ingest",
      cue_count: cues.length,
      chunk_count: chunks.length,
    },
    ingest_status: "ready",
    updated_at: new Date().toISOString(),
  };

  const { error: sourceErr } = await sb
    .from("knowledge_sources")
    .upsert(sourcePayload, { onConflict: "source_key" });
  if (sourceErr) {
    return json({ errorMessage: "source upsert failed: " + sourceErr.message }, 500);
  }

  const { data: sourceRows, error: sidErr } = await sb
    .from("knowledge_sources")
    .select("id")
    .eq("source_key", sourceKey)
    .limit(1);
  if (sidErr || !sourceRows?.length) {
    return json({
      errorMessage: "source id resolve failed: " + (sidErr?.message || "empty"),
    }, 500);
  }
  const sourceId = sourceRows[0].id as number;

  // Replace previous chunks for this source to avoid orphans with different keys
  await sb.from("knowledge_chunks").delete().eq("source_id", sourceId);

  const chunkPayload = chunks.map((c) => ({
    source_id: sourceId,
    chunk_key: c.chunk_key,
    start_sec: c.start_sec,
    end_sec: c.end_sec,
    speaker: c.speaker,
    content: c.content,
    content_hash: c.content_hash,
    search_text: c.search_text,
  }));

  for (let i = 0; i < chunkPayload.length; i += 100) {
    const slice = chunkPayload.slice(i, i + 100);
    const { error: chunkErr } = await sb
      .from("knowledge_chunks")
      .upsert(slice, { onConflict: "chunk_key" });
    if (chunkErr) {
      return json({ errorMessage: "chunk upsert failed: " + chunkErr.message }, 500);
    }
  }

  let embedded = 0;
  let embedError: string | null = null;
  if (!skipEmbed) {
    try {
      const toEmbed = chunks.slice(0, MAX_EMBED_CHUNKS);
      for (const c of toEmbed) {
        const values = await embedDocument(c.content.slice(0, 8000));
        const { error: embErr } = await sb
          .from("knowledge_chunks")
          .update({ embedding: values })
          .eq("chunk_key", c.chunk_key);
        if (embErr) throw new Error(embErr.message);
        embedded += 1;
      }
    } catch (e) {
      embedError = e instanceof Error ? e.message : String(e);
    }
  }

  return json({
    ok: true,
    source_key: sourceKey,
    source_id: sourceId,
    title,
    video_id: videoId,
    video_url: videoUrl,
    instructor,
    cue_count: cues.length,
    chunk_count: chunks.length,
    embedded_count: embedded,
    pending_embed: Math.max(0, chunks.length - embedded),
    embed_error: embedError,
    chunks: chunks.map((c) => ({
      chunk_key: c.chunk_key,
      source_key: sourceKey,
      start_sec: c.start_sec,
      end_sec: c.end_sec,
      speaker: c.speaker,
      content: c.content,
      search_text: c.search_text,
    })),
    note:
      embedded < chunks.length
        ? "一部または全部の embedding は未完了の可能性があります。意味検索に載らない場合は embed_to_supabase.py を実行してください。"
        : null,
  });
});
