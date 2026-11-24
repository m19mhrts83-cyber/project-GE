import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { loadDeskCards } from "@/lib/desk";
import { loadOpenTopics312 } from "@/lib/topics312";
import { cleanupItem, mailItem, sortItems, topicItem, type AllItem } from "@/lib/allCore";
import type { CleanupSnapshot } from "@/lib/cleanupBulk";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** まとめて判断の一覧。メール・片付け・お題を集めて、重要度の順に返す。読めなかったジャンルは errors に出す（空と区別する） */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const today = new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 10);
  const items: AllItem[] = [];
  const errors: string[] = [];

  await Promise.all([
    (async () => {
      try {
        items.push(...(await loadDeskCards(sb, { limit: 60 })).map(mailItem));
      } catch (e) {
        errors.push(`メール: ${e instanceof Error ? e.message : String(e)}`);
      }
    })(),
    (async () => {
      try {
        const { data, error } = await sb.from("sync_meta").select("value").eq("key", "todoist_cleanup_snapshot").maybeSingle();
        if (error) throw new Error(error.message);
        const snap = data?.value ? (JSON.parse(String(data.value)) as CleanupSnapshot) : null;
        items.push(...(snap?.cards || []).map((c) => cleanupItem(c, today)));
      } catch (e) {
        errors.push(`片付け: ${e instanceof Error ? e.message : String(e)}`);
      }
    })(),
    (async () => {
      try {
        items.push(...(await loadOpenTopics312(sb)).map(topicItem));
      } catch (e) {
        errors.push(`お題: ${e instanceof Error ? e.message : String(e)}`);
      }
    })(),
  ]);

  return NextResponse.json({ ok: true, items: sortItems(items), errors }, { headers: { "cache-control": "private, no-store" } });
}
