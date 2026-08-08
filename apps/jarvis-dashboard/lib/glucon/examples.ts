/** kamiooya-qa から活動報告・成果報告の参考例を取得（読取のみ） */

import { kamiooyaAdminOrNull } from "@/lib/kamiooya/client";
import type { GluconExample, GluconReportKind } from "./types";

const CATEGORY: Record<GluconReportKind, string> = {
  activity: "月次活動報告",
  result: "成果報告",
};

function excerpt(content: string, max = 420): string {
  const t = (content || "").replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}

export async function fetchGluconExamples(
  kind: GluconReportKind,
  limit = 4,
): Promise<{ ok: true; examples: GluconExample[] } | { ok: false; error: string }> {
  const sb = kamiooyaAdminOrNull();
  if (!sb) {
    return {
      ok: false,
      error: "神大家DB未配線（SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY）",
    };
  }

  const { data, error } = await sb
    .from("comments")
    .select("comment_id, author_name, posted_at, content")
    .eq("forum_category", CATEGORY[kind])
    .or("is_deleted.is.null,is_deleted.eq.false")
    .not("content", "is", null)
    .order("posted_at", { ascending: false })
    .limit(40);

  if (error) {
    return { ok: false, error: error.message };
  }

  const scored = (data || [])
    .map((r) => {
      const content = String(r.content || "");
      const len = content.length;
      const structured =
        (kind === "activity" && content.includes("■1■")) ||
        (kind === "result" && (content.includes("■【") || content.includes("所感")));
      const score = (structured ? 1000 : 0) + Math.min(len, 2000);
      return { r, score, content };
    })
    .filter((x) => x.content.length >= 80)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  return {
    ok: true,
    examples: scored.map(({ r, content }) => ({
      comment_id: String(r.comment_id),
      author_name: String(r.author_name || ""),
      posted_at: r.posted_at ? String(r.posted_at) : null,
      excerpt: excerpt(content),
    })),
  };
}

export async function fetchGluconLessonRows(): Promise<
  | {
      ok: true;
      rows: Array<{ comment_id: string; lesson_title: string }>;
    }
  | { ok: false; error: string }
> {
  const sb = kamiooyaAdminOrNull();
  if (!sb) {
    return {
      ok: false,
      error: "神大家DB未配線（SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY）",
    };
  }

  const { data, error } = await sb
    .from("comments")
    .select("comment_id, lesson_title")
    .eq("course_tab", "神大家4.グルコン")
    .eq("source_kind", "lesson_desc")
    .not("lesson_title", "is", null)
    .limit(200);

  if (error) {
    return { ok: false, error: error.message };
  }

  return {
    ok: true,
    rows: (data || []).map((r) => ({
      comment_id: String(r.comment_id),
      lesson_title: String(r.lesson_title || ""),
    })),
  };
}
