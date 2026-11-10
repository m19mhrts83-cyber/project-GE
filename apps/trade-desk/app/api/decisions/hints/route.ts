import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { loadDecisionRows } from "@/lib/kurashiftDecisionLoad";
import { buildHints } from "@/lib/kurashiftDecisionLog";

/**
 * 判断メモに出すヒント（同じ種類の過去の判断）。
 * GET /api/decisions/hints?ctx=money:approved
 * 本人の過去の記録をそのまま引くだけで、AI は呼ばない。
 */
export async function GET(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const ctx = new URL(req.url).searchParams.get("ctx") || "";
  if (!/^(money|deal):[a-z_]{2,30}$/.test(ctx)) {
    return NextResponse.json({ error: "ctx required" }, { status: 400 });
  }
  const rows = await loadDecisionRows(supabase, 365);
  return NextResponse.json({ ok: true, hints: buildHints(rows, ctx) });
}
