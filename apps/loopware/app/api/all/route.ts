import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { loadDeskCards } from "@/lib/desk";
import { loadOpenTopics312 } from "@/lib/topics312";
import { loadRules } from "@/lib/rules";
import { pendingFixes } from "@/lib/zaimCore";
import {
  cleanupItem,
  mailItem,
  ruleItem,
  sortItems,
  topicItem,
  weekItem,
  weightMap,
  zaimItem,
  type AllItem,
} from "@/lib/allCore";
import type { CleanupSnapshot } from "@/lib/cleanupBulk";
import type { Snapshot as WeekSnapshot } from "@/lib/weekPick";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * まとめて判断の一覧。メール・片付け（318／313／スター）・お題・今週の9件・Zaim・ルール候補を集めて、重要度の順に返す。
 * 読めなかったジャンルは errors に出す（空と区別する）。
 */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const today = new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 10);
  const items: AllItem[] = [];
  const errors: string[] = [];
  const wrap = (label: string, fn: () => Promise<void>) =>
    fn().catch((e) => {
      errors.push(`${label}: ${e instanceof Error ? e.message : String(e)}`);
    });

  // 判断の重さ（すぐ決まる／じっくり）は今週の9件の材料から引く。読めなくても片付けは出す（印が付かないだけ）
  let week: WeekSnapshot | null = null;
  await wrap("今週の9件", async () => {
    const { data, error } = await sb.from("sync_meta").select("value").eq("key", "weekly_pick_snapshot").maybeSingle();
    if (error) throw new Error(error.message);
    week = data?.value ? (JSON.parse(String(data.value)) as WeekSnapshot) : null;
  });
  const weights = weightMap(week);

  await Promise.all([
    wrap("メール", async () => {
      items.push(...(await loadDeskCards(sb, { limit: 60 })).map(mailItem));
    }),
    wrap("片付け", async () => {
      const { data, error } = await sb.from("sync_meta").select("value").eq("key", "todoist_cleanup_snapshot").maybeSingle();
      if (error) throw new Error(error.message);
      const snap = data?.value ? (JSON.parse(String(data.value)) as CleanupSnapshot) : null;
      items.push(...(snap?.cards || []).map((c) => cleanupItem(c, today, weights)));
    }),
    wrap("お題", async () => {
      items.push(...(await loadOpenTopics312(sb)).map(topicItem));
    }),
    wrap("今週の9件", async () => {
      const w = week as WeekSnapshot | null;
      if (!w?.week) return;
      const { data, error } = await sb
        .from("owner_decisions")
        .select("id")
        .eq("surface", "weekly_pick")
        .eq("action", "commit")
        .eq("target_id", w.week)
        .limit(1)
        .maybeSingle();
      if (error) throw new Error(error.message);
      const it = weekItem(w, !!data, today);
      if (it) items.push(it);
    }),
    wrap("Zaim", async () => {
      const { data, error } = await sb.from("watch_status").select("payload").eq("id", "zaim_quality").maybeSingle();
      if (error) throw new Error(error.message);
      items.push(...pendingFixes((data?.payload || {}) as Record<string, unknown>).map(zaimItem));
    }),
    wrap("ルール候補", async () => {
      const r = await loadRules(sb);
      const decided = new Set(r.decided);
      items.push(...r.candidates.filter((c) => !decided.has(c.id)).map(ruleItem));
    }),
  ]);

  return NextResponse.json({ ok: true, items: sortItems(items), errors, today }, { headers: { "cache-control": "private, no-store" } });
}
