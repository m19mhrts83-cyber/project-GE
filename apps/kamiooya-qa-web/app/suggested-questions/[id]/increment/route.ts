import { NextResponse } from "next/server";
import { requireUser } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { withErrorHandler } from "@/lib/routeHandler";

export const runtime = "nodejs";

export const PUT = withErrorHandler(async (req, { params }) => {
  requireUser(req);
  const { id } = await params;
  const sb = supabaseAdmin();
  const { data: row, error: fetchErr } = await sb
    .from("suggested_questions")
    .select("id,frequency")
    .eq("id", id)
    .maybeSingle();
  if (fetchErr || !row) {
    return NextResponse.json({ errorMessage: "対象が見つかりません" }, { status: 404 });
  }
  const next = Number(row.frequency || 0) + 1;
  const { error } = await sb.from("suggested_questions").update({ frequency: next }).eq("id", id);
  if (error) {
    return NextResponse.json({ errorMessage: error.message || "更新に失敗しました" }, { status: 500 });
  }
  return NextResponse.json({ success: true });
});
