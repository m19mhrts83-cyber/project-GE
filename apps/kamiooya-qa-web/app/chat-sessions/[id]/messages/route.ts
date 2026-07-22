import { NextResponse } from "next/server";
import { requireUser } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { toDbId } from "@/lib/ids";
import { withErrorHandler } from "@/lib/routeHandler";
import {
  buildAnswerWithCitations,
  searchKnowledge,
  type Citation,
} from "@/lib/knowledgeSearch";

export const runtime = "nodejs";

export const POST = withErrorHandler(async (req, { params }) => {
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

  let citations: Citation[] = [];
  try {
    citations = await searchKnowledge(content, 10);
  } catch (e) {
    console.error("searchKnowledge failed", e);
    citations = [];
  }
  const { answer } = buildAnswerWithCitations(content, citations);

  await sb.from("chat_messages").insert([{ session_id: sessionDbId, role: "assistant", content: answer }]);

  return NextResponse.json({ answer, citations });
});
