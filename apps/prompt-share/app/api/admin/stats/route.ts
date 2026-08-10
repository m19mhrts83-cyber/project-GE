import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

function errRes(e: unknown) {
  const status = (e as { status?: number })?.status || 500;
  const message = e instanceof Error ? e.message : "error";
  return NextResponse.json({ error: message }, { status });
}

export async function GET(req: Request) {
  try {
    requireAdmin(req);
    const sb = supabaseAdmin();
    const { data: prompts, error } = await sb
      .from("prompts")
      .select("id,title,public_token,status,view_count,generate_count,copy_count")
      .order("copy_count", { ascending: false });
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });

    const { data: events } = await sb
      .from("prompt_usage_events")
      .select("prompt_id,event_type")
      .order("id", { ascending: false })
      .limit(5000);

    const byPrompt: Record<string, Record<string, number>> = {};
    for (const ev of events || []) {
      const pid = String(ev.prompt_id);
      if (!byPrompt[pid]) byPrompt[pid] = {};
      byPrompt[pid][ev.event_type] = (byPrompt[pid][ev.event_type] || 0) + 1;
    }

    const rows = (prompts || []).map((p) => ({
      ...p,
      events: byPrompt[String(p.id)] || {}
    }));

    return NextResponse.json({ stats: rows });
  } catch (e) {
    return errRes(e);
  }
}
