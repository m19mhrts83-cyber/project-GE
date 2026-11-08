import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { loadRules } from "@/lib/rules";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: true, persisted: false, week: null, candidates: [], adopted: [], decided: [] });
  try {
    return NextResponse.json({ ok: true, persisted: true, ...(await loadRules(sb)) }, { headers: { "cache-control": "private, no-store" } });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
