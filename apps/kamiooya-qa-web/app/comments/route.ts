import { NextResponse } from "next/server";
import { requireUser } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function GET(req: Request) {
  requireUser(req);
  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("comments")
    .select("*")
    .order("posted_at", { ascending: false, nullsFirst: false })
    .limit(50000);

  if (error) {
    return NextResponse.json({ errorMessage: error.message || "取得に失敗しました" }, { status: 500 });
  }
  return NextResponse.json({ comments: data ?? [] });
}

