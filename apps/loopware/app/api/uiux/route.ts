import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { loadUiux } from "@/lib/uiux";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const sb = serviceClient();
  if (!sb) {
    return NextResponse.json({ ok: true, persisted: false, round: null, rules: [], decided: {}, picked: null, recent: { works: 0, firstOk: 0, avgTrips: null } });
  }
  try {
    return NextResponse.json({ ok: true, persisted: true, ...(await loadUiux(sb)) }, { headers: { "cache-control": "private, no-store" } });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
