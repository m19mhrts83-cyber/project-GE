import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function GET(req: Request) {
  requireAdmin(req);
  const sb = supabaseAdmin();
  const { data, error } = await sb.from("users").select("id,email,status").eq("status", "pending");
  if (error) {
    return NextResponse.json({ errorMessage: error.message || "取得に失敗しました" }, { status: 500 });
  }
  return NextResponse.json({ users: data ?? [] });
}

