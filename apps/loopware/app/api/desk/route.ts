import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { dashboardBase, loadDeskCards, loadLeftCards } from "@/lib/desk";
import { tally, weekStartIso } from "@/lib/decisionContract";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** 判断デスクのカード。?surface=triage&item=<triage_item_id>、残り案件は &view=left */
export async function GET(req: Request) {
  const u = new URL(req.url);
  const surface = u.searchParams.get("surface") || "triage";
  if (surface !== "triage") {
    return NextResponse.json({ ok: false, error: "この画面はまだメール（triage）だけです" }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: true, persisted: false, cards: [], tally: tally([]), dashboard: dashboardBase() });
  try {
    const view = u.searchParams.get("view");
    const cards =
      view === "left" ? await loadLeftCards(sb) : await loadDeskCards(sb, { item: u.searchParams.get("item") });
    const { data } = await sb
      .from("owner_decisions")
      .select("action,payload")
      .like("surface", "triage%")
      .gte("decided_at", weekStartIso())
      .limit(2000);
    return NextResponse.json(
      { ok: true, persisted: true, cards, tally: tally(data || []), dashboard: dashboardBase() },
      { headers: { "cache-control": "private, no-store" } },
    );
  } catch (e) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
