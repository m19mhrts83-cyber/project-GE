import { NextResponse } from "next/server";
import { requireUser } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { toDbId } from "@/lib/ids";

export const runtime = "nodejs";

function extractKeyword(text: unknown): string {
  const s = String(text || "").trim();
  if (!s) return "";
  // 超単純: 先頭から「それっぽい」語を拾う（日本語/英数字の連続）
  const m = s.match(/[0-9A-Za-zぁ-んァ-ン一-龥]{2,}/g);
  if (!m || m.length === 0) return s.slice(0, 6);
  // よくある語は避ける
  const stop = new Set(["です", "ます", "こと", "方法", "教えて", "ください", "どこ", "なに", "何"]);
  for (const w of m) {
    if (!stop.has(w)) return w;
  }
  return m[0];
}

type CommentRow = {
  id?: string;
  source_type?: string | null;
  comment_id?: string | null;
  posted_at?: string | null;
  author_name?: string | null;
  content?: string | null;
};

function buildAnswer(message: string, comments: CommentRow[]) {
  const lines = [];
  lines.push("参照データから関連しそうな情報を見つけました。");
  lines.push("");
  if (!comments || comments.length === 0) {
    lines.push("該当するコメントが見つかりませんでした。キーワードを変えて再度お試しください。");
    return lines.join("\n");
  }
  lines.push("参考（上位）:");
  for (const c of comments.slice(0, 5)) {
    const meta = `[${c.source_type || "不明"}] ${c.posted_at || ""} ${c.author_name || ""} #${c.comment_id || c.id}`;
    lines.push(`- ${meta}`);
    lines.push(`  - ${(c.content || "").toString().replace(/\s+/g, " ").slice(0, 220)}`);
  }
  return lines.join("\n");
}

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const u = requireUser(req);
  const { id: sessionId } = await params;
  const sessionDbId = toDbId(sessionId);
  const body = (await req.json().catch(() => null)) || {};
  const content = String(body.content || "").trim();
  if (!content) return NextResponse.json({ errorMessage: "質問が空です" }, { status: 400 });

  const sb = supabaseAdmin();
  const { data: session } = await sb
    .from("chat_sessions")
    .select("id,user_id")
    .eq("id", sessionDbId)
    .maybeSingle();
  if (!session) return NextResponse.json({ errorMessage: "not_found" }, { status: 404 });
  if (session.user_id !== u.id && u.role !== "admin") {
    return NextResponse.json({ errorMessage: "forbidden" }, { status: 403 });
  }

  await sb.from("chat_messages").insert([{ session_id: sessionDbId, role: "user", content }]);

  const keyword = extractKeyword(content);
  const { data: related } = await sb
    .from("comments")
    .select("*")
    .ilike("content", `%${keyword}%`)
    .limit(10);

  const answer = buildAnswer(content, related || []);
  await sb.from("chat_messages").insert([{ session_id: sessionDbId, role: "assistant", content: answer }]);

  return NextResponse.json({ answer });
}

