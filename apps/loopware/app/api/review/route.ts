import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";

export const runtime = "nodejs";

/** 週次レビュー用：期間内の判断ログ（312 の task_loop、313・音声・基準・レビューの owner_decisions）を返す。 */
export async function GET(req: Request) {
  const u = new URL(req.url);
  const from = u.searchParams.get("from") || "";
  const to = u.searchParams.get("to") || "";
  const sb = serviceClient();
  if (!sb || !from || !to) {
    return NextResponse.json({ ok: true, configured: false, items: [], voice: [], lastReview: null });
  }
  try {
    const items: unknown[] = [];

    const { data: ds } = await sb
      .from("task_loop_decisions")
      .select("topic_id, chosen_index, choice, final_text, before_text, after_text, reason_tags, free_note, updated_at")
      .gte("updated_at", from)
      .lt("updated_at", to)
      .order("updated_at", { ascending: false })
      .limit(500);
    const ids = (ds || []).map((d) => d.topic_id);
    const topics: Record<string, string> = {};
    if (ids.length) {
      const { data: ts } = await sb.from("task_loop_topics").select("id, topic_text").in("id", ids);
      (ts || []).forEach((t) => (topics[t.id] = t.topic_text));
    }
    (ds || []).forEach((d) =>
      items.push({
        at: d.updated_at,
        agent: "312",
        title: (topics[d.topic_id] || "").split("\n")[0].slice(0, 80),
        choice: d.choice,
        reasons: d.reason_tags || [],
        note: String(d.free_note || "").replace(/^【次も同じに】/, ""),
        before: d.before_text || "",
        after: d.after_text || "",
        scope: String(d.free_note || "").startsWith("【次も同じに】") ? "rule" : "once",
      }),
    );

    const { data: od } = await sb
      .from("owner_decisions")
      .select("decided_at, surface, action, subject, note, payload")
      .in("surface", ["todoist_313", "loopware_voice"])
      .gte("decided_at", from)
      .lt("decided_at", to)
      .order("decided_at", { ascending: false })
      .limit(500);
    const voice: unknown[] = [];
    (od || []).forEach((r) => {
      const p = (r.payload || {}) as Record<string, unknown>;
      if (r.surface === "loopware_voice") {
        if (r.action === "voice_comment")
          voice.push({ at: r.decided_at, target: r.subject, text: r.note });
        return;
      }
      if (p.kind !== "loopware") return;
      items.push({
        at: r.decided_at,
        agent: "313",
        title: String(r.subject || "").slice(0, 80),
        choice: r.action,
        reasons: (p.reason_tags as string[]) || [],
        note: r.note || "",
        before: String(p.before_text || ""),
        after: String(p.after_text || ""),
        scope: String(p.scope || "once"),
      });
    });

    const { data: dd } = await sb
      .from("owner_decisions")
      .select("target_id, note")
      .eq("surface", "loopware_daily")
      .eq("action", "daily_done")
      .gte("decided_at", from)
      .lt("decided_at", to);
    const dailyDone = Array.from(new Set((dd || []).map((r) => r.target_id)));

    const { data: lr } = await sb
      .from("owner_decisions")
      .select("decided_at, payload")
      .eq("surface", "loopware_review")
      .order("decided_at", { ascending: false })
      .limit(1);
    return NextResponse.json({
      ok: true,
      configured: true,
      items,
      voice,
      dailyDone,
      lastReview: lr?.[0]?.decided_at ?? null,
    });
  } catch (e) {
    return NextResponse.json({
      ok: true,
      configured: false,
      items: [],
      voice: [],
      lastReview: null,
      reason: e instanceof Error ? e.message : String(e),
    });
  }
}
