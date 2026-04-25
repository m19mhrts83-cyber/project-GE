import { NextResponse } from "next/server";
import { requireUser } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const u = requireUser(req);
  const { id } = await params;
  if (id !== u.id) {
    return NextResponse.json({ errorMessage: "forbidden" }, { status: 403 });
  }
  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("chat_sessions")
    .select("id,title,created_at")
    .eq("user_id", id)
    .order("created_at", { ascending: false });
  if (error) {
    return NextResponse.json({ errorMessage: error.message || "取得に失敗しました" }, { status: 500 });
  }
  return NextResponse.json({ sessions: data ?? [] });
}

