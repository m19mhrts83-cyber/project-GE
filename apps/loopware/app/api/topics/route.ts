import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { loadOpenTopics312 } from "@/lib/topics312";

export const runtime = "nodejs";

/** 312 の本物のお題（Slack の発言など）。発言の中身を返すので鍵が要る（middleware） */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: true, persisted: false, topics: [] });
  try {
    const topics = await loadOpenTopics312(sb);
    return NextResponse.json({ ok: true, persisted: true, topics }, { headers: { "cache-control": "private, no-store" } });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
