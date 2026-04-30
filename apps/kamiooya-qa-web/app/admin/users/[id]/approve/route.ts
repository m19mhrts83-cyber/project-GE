import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { withErrorHandler } from "@/lib/routeHandler";

export const runtime = "nodejs";

export const PUT = withErrorHandler(async (req, { params }) => {
  requireAdmin(req);
  const { id } = await params;
  const sb = supabaseAdmin();
  const { error } = await sb.from("users").update({ status: "approved" }).eq("id", id);
  if (error) {
    return NextResponse.json({ errorMessage: error.message || "更新に失敗しました" }, { status: 500 });
  }
  return NextResponse.json({ success: true });
});
