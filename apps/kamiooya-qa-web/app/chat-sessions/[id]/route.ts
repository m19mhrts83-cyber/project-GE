import { NextResponse } from "next/server";
import { requireUser } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const u = requireUser(req);
  const { id } = await params;
  const sb = supabaseAdmin();

  const { data: session, error: sErr } = await sb
    .from("chat_sessions")
    .select("id,user_id,title,created_at")
    .eq("id", id)
    .maybeSingle();
  if (sErr || !session) {
    return NextResponse.json({ errorMessage: "not_found" }, { status: 404 });
  }
  if (session.user_id !== u.id && u.role !== "admin") {
    return NextResponse.json({ errorMessage: "forbidden" }, { status: 403 });
  }

  const { data: messages, error: mErr } = await sb
    .from("chat_messages")
    .select("id,role,content,created_at")
    .eq("session_id", id)
    .order("created_at", { ascending: true });
  if (mErr) {
    return NextResponse.json({ errorMessage: mErr.message || "取得に失敗しました" }, { status: 500 });
  }

  return NextResponse.json({ session, messages: messages ?? [] });
}

