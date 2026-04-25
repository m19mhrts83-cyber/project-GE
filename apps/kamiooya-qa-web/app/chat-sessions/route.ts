import { NextResponse } from "next/server";
import { requireUser } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const u = requireUser(req);
  const body = (await req.json().catch(() => null)) as { user_id?: string; initial_message?: string } | null;
  const userId = String(body?.user_id ?? "");
  if (!userId || userId !== u.id) {
    return NextResponse.json({ errorMessage: "user_id が不正です" }, { status: 400 });
  }
  const initial = String(body?.initial_message ?? "").trim();
  const title = initial ? initial.slice(0, 24) : "無題";
  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("chat_sessions")
    .insert([{ user_id: userId, title }])
    .select("id,title,created_at")
    .single();
  if (error) {
    return NextResponse.json({ errorMessage: error.message || "作成に失敗しました" }, { status: 400 });
  }
  return NextResponse.json({ id: data.id, title: data.title, created_at: data.created_at });
}

