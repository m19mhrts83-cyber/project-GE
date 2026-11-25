import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import type { CleanupSnapshot } from "@/lib/cleanupBulk";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * タブのバッジ用の「残り件数」。
 * topics=312の決めていないお題／missIds=提案を仕分ける候補／cleanup=まとめて片付ける候補。
 * 読めなかったものは null（0件と区別する）。閉じ漏れ=Macの検知結果（origin leak のカード）の件数。cleanup はそれを除く。
 */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const out: { topics: number | null; missIds: string[] | null; cleanup: number | null; closeLeak: number | null } = {
    topics: null,
    missIds: null,
    cleanup: null,
    closeLeak: null,
  };
  await Promise.all([
    (async () => {
      const { data, error } = await sb
        .from("task_loop_topics")
        .select("id")
        .eq("agent_id", "312")
        .eq("status", "open")
        .neq("source_kind", "seed")
        .limit(100);
      if (!error) out.topics = (data || []).length;
    })(),
    (async () => {
      const { data, error } = await sb.from("sync_meta").select("value").eq("key", "loopware_312_candidates").maybeSingle();
      if (error) return;
      try {
        const raw = data?.value;
        const j = (typeof raw === "string" ? JSON.parse(raw) : raw) as { candidates?: unknown[] } | null;
        out.missIds = Array.isArray(j?.candidates) ? j!.candidates!.map((_, i) => `miss-${i + 1}`) : [];
      } catch {
        /* null のまま */
      }
    })(),
    (async () => {
      const { data, error } = await sb.from("sync_meta").select("value").eq("key", "todoist_cleanup_snapshot").maybeSingle();
      if (error) return;
      try {
        const snap = data?.value ? (JSON.parse(String(data.value)) as CleanupSnapshot) : null;
        const cs = snap?.cards ?? [];
        out.closeLeak = cs.filter((c) => c.origin === "leak").length;
        out.cleanup = cs.length - out.closeLeak;
      } catch {
        /* null のまま */
      }
    })(),
  ]);
  return NextResponse.json({ ok: true, ...out }, { headers: { "cache-control": "private, no-store" } });
}
