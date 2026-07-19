import { supabaseAdmin } from "@/lib/supabaseAdmin";

export type Citation = {
  kind: "comment" | "video_chunk";
  sourceType: string;
  commentId?: string | null;
  chunkKey?: string | null;
  authorName?: string | null;
  postedAt?: string | null;
  videoTitle?: string | null;
  videoUrl?: string | null;
  startSec?: number | null;
  endSec?: number | null;
  startLabel?: string | null;
  snippet: string;
  score: number;
};

const STOP = new Set(["です", "ます", "こと", "方法", "教えて", "ください", "どこ", "なに", "何", "について"]);

export function tokenizeQuery(text: unknown): string[] {
  const s = String(text || "").trim();
  if (!s) return [];
  const m = s.match(/[0-9A-Za-zぁ-んァ-ン一-龥]{2,}/g) || [];
  const out: string[] = [];
  for (const w of m) {
    if (STOP.has(w)) continue;
    if (!out.includes(w)) out.push(w);
    if (out.length >= 6) break;
  }
  if (out.length === 0 && s) out.push(s.slice(0, 12));
  return out;
}

export function formatMmSs(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || Number.isNaN(Number(sec))) return "";
  const s = Math.max(0, Math.floor(Number(sec)));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  return `${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

function withVideoTimeUrl(url: string | null | undefined, startSec: number | null | undefined): string | null {
  if (!url) return null;
  if (startSec === null || startSec === undefined) return url;
  if (/[?&]t=/.test(url)) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}t=${Math.floor(startSec)}`;
}

function scoreText(text: string, tokens: string[]): number {
  const lower = text.toLowerCase();
  let score = 0;
  for (const t of tokens) {
    if (lower.includes(t.toLowerCase())) score += 1;
  }
  return score;
}

/** コメント＋動画チャンクを横断検索（複数語 AND に近い加点） */
export async function searchKnowledge(query: string, limit = 10): Promise<Citation[]> {
  const tokens = tokenizeQuery(query);
  if (tokens.length === 0) return [];
  const sb = supabaseAdmin();
  const primary = tokens[0];

  const { data: comments } = await sb
    .from("comments")
    .select("source_type,comment_id,posted_at,author_name,content")
    .ilike("content", `%${primary}%`)
    .limit(40);

  let chunkRows: Array<Record<string, unknown>> = [];
  try {
    const { data: chunks, error } = await sb
      .from("knowledge_chunks")
      .select("chunk_key,start_sec,end_sec,speaker,content,knowledge_sources(title,video_url,video_id,source_key)")
      .ilike("content", `%${primary}%`)
      .limit(40);
    if (!error && chunks) chunkRows = chunks as Array<Record<string, unknown>>;
  } catch {
    chunkRows = [];
  }

  const hits: Citation[] = [];

  for (const c of comments || []) {
    const content = String(c.content || "");
    const score = scoreText(content, tokens);
    if (score <= 0) continue;
    hits.push({
      kind: "comment",
      sourceType: String(c.source_type || "WeStudy"),
      commentId: c.comment_id,
      authorName: c.author_name,
      postedAt: c.posted_at,
      snippet: content.replace(/\s+/g, " ").slice(0, 220),
      score,
    });
  }

  for (const row of chunkRows) {
    const content = String(row.content || "");
    const score = scoreText(content, tokens) + 1;
    if (score <= 1 && tokens.length > 1) {
      // primary matched via query; still keep if any token hits
      if (!tokens.some((t) => content.toLowerCase().includes(t.toLowerCase()))) continue;
    }
    const src = (row.knowledge_sources || {}) as Record<string, unknown>;
    const startSec = row.start_sec === null || row.start_sec === undefined ? null : Number(row.start_sec);
    const videoUrl = withVideoTimeUrl(
      (src.video_url as string) || null,
      startSec
    );
    hits.push({
      kind: "video_chunk",
      sourceType: "WeStudy動画",
      chunkKey: String(row.chunk_key || ""),
      videoTitle: (src.title as string) || null,
      videoUrl,
      startSec,
      endSec: row.end_sec === null || row.end_sec === undefined ? null : Number(row.end_sec),
      startLabel: formatMmSs(startSec),
      authorName: (row.speaker as string) || null,
      snippet: content.replace(/\s+/g, " ").slice(0, 220),
      score,
    });
  }

  hits.sort((a, b) => b.score - a.score || (a.kind === "video_chunk" ? -1 : 1));
  return hits.slice(0, limit);
}

export function buildAnswerWithCitations(message: string, citations: Citation[]): {
  answer: string;
  citations: Citation[];
} {
  const lines: string[] = [];
  lines.push("参照データから関連しそうな情報を見つけました。");
  lines.push("");
  if (!citations.length) {
    lines.push("該当する情報が見つかりませんでした。キーワードを変えて再度お試しください。");
    return { answer: lines.join("\n"), citations };
  }
  lines.push("参考（上位）:");
  for (const c of citations.slice(0, 5)) {
    if (c.kind === "video_chunk") {
      const when = c.startLabel ? `${c.startLabel}（${c.startSec}秒）` : "";
      lines.push(`- [WeStudy動画] ${c.videoTitle || "（タイトル不明）"} — ${when}`);
      if (c.videoUrl) lines.push(`  - URL: ${c.videoUrl}`);
      lines.push(`  - ${(c.authorName ? c.authorName + ": " : "") + c.snippet}`);
    } else {
      lines.push(
        `- [${c.sourceType}] ${c.postedAt || ""} ${c.authorName || ""} #${c.commentId || ""}`
      );
      lines.push(`  - ${c.snippet}`);
    }
  }
  return { answer: lines.join("\n"), citations };
}
