import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import type { EventType } from "@/lib/prompts";

export const runtime = "nodejs";

const COUNT_COL: Partial<Record<EventType, string>> = {
  view: "view_count",
  generate: "generate_count",
  copy: "copy_count"
};

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as
    | { prompt_id?: number; public_token?: string; event_type?: EventType }
    | null;
  const eventType = body?.event_type;
  const allowed: EventType[] = [
    "view",
    "generate",
    "copy",
    "open_chatgpt",
    "open_gemini",
    "open_claude",
    "open_aistudio"
  ];
  if (!eventType || !allowed.includes(eventType)) {
    return NextResponse.json({ error: "invalid event_type" }, { status: 400 });
  }

  const sb = supabaseAdmin();
  let promptId = body?.prompt_id ? Number(body.prompt_id) : 0;
  if (!promptId && body?.public_token) {
    const { data } = await sb
      .from("prompts")
      .select("id,status,access_level")
      .eq("public_token", String(body.public_token))
      .maybeSingle();
    if (!data || data.status !== "published" || data.access_level !== "public") {
      return NextResponse.json({ error: "not found" }, { status: 404 });
    }
    promptId = Number(data.id);
  }
  if (!promptId) {
    return NextResponse.json({ error: "prompt_id required" }, { status: 400 });
  }

  const { error: evErr } = await sb.from("prompt_usage_events").insert({
    prompt_id: promptId,
    event_type: eventType
  });
  if (evErr) {
    return NextResponse.json({ error: evErr.message }, { status: 500 });
  }

  const col = COUNT_COL[eventType];
  if (col) {
    const { data: row } = await sb.from("prompts").select(col).eq("id", promptId).maybeSingle();
    const current = Number((row as Record<string, unknown> | null)?.[col] ?? 0);
    await sb
      .from("prompts")
      .update({ [col]: current + 1, updated_at: new Date().toISOString() })
      .eq("id", promptId);
  }

  return NextResponse.json({ ok: true });
}
