import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { loadCloseLeak } from "@/lib/closeLeakLoad";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * 313 閉じ漏れの候補（読み取りのみ。鍵が要る）。
 * 確定は /api/cleanup（payload.origin=close_leak）に送り、30 分ごとの reflect が Todoist に反映する。
 */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  try {
    const { snapshot, cards } = await loadCloseLeak(sb);
    return NextResponse.json(
      { ok: true, generated_at: snapshot?.generated_at ?? null, connected: !!snapshot, cards },
      { headers: { "cache-control": "private, no-store" } },
    );
  } catch (e) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
