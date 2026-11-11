import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { loadSlides } from "@/lib/slides";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: true, persisted: false, deck: null, rules: [], decided: {}, planned: null });
  try {
    return NextResponse.json({ ok: true, persisted: true, ...(await loadSlides(sb)) }, { headers: { "cache-control": "private, no-store" } });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
