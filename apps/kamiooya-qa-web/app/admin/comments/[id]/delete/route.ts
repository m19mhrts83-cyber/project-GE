import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  requireAdmin(req);
  const { id } = await params;
  const sb = supabaseAdmin();
  const { error } = await sb.from("comments").delete().eq("id", id);
  if (error) {
    return NextResponse.json({ errorMessage: error.message || "削除に失敗しました" }, { status: 500 });
  }
  return NextResponse.json({ success: true });
}

