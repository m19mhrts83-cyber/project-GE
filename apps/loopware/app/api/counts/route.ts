import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import type { CleanupSnapshot } from "@/lib/cleanupBulk";
import { loadCloseLeak } from "@/lib/closeLeakLoad";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * タブのバッジ用の「残り件数」。
 * topics=312の決めていないお題／missIds=提案を仕分ける候補／cleanup=まとめて片付ける候補。
 * closeLeak=313 閉じ漏れ（Mac の検知が sync_meta.todoist_313_close_leak に置いた件のうち未判断）。
 * 読めなかったもの・まだ一度も置かれていないものは null（0件と区別する）。
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
        out.cleanup = snap?.cards?.length ?? 0;
      } catch {
        /* null のまま */
      }
    })(),
    (async () => {
      try {
        const { snapshot, cards } = await loadCloseLeak(sb);
        out.closeLeak = snapshot ? cards.length : null;
      } catch {
        /* null のまま */
      }
    })(),
  ]);
  return NextResponse.json({ ok: true, ...out }, { headers: { "cache-control": "private, no-store" } });
}
