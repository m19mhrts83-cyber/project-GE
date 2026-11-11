/**
 * 資料作成ループの読み込み（サーバ専用）。
 * いまの資料（デッキ）は sync_meta.loopware_slides に、エージェントが scripts/slides_loop.py で置く。
 * 判断は owner_decisions（surface = slide_plan / slide_rule）。
 */
import type { SupabaseClient } from "@supabase/supabase-js";
import { adoptedSlideRules, decidedProposals, parseDeck, type SlideDeck, type SlideRule } from "@/lib/slidesCore";

export const SLIDES_META_KEY = "loopware_slides";

export type SlidesState = {
  deck: SlideDeck | null;
  rules: SlideRule[];
  decided: Record<string, string>;
  planned: { plan: string | null; axes: Record<string, string>; at: string } | null;
};

export async function loadDeck(sb: SupabaseClient): Promise<SlideDeck | null> {
  const { data } = await sb.from("sync_meta").select("value").eq("key", SLIDES_META_KEY).maybeSingle();
  return data ? parseDeck(data.value) : null;
}

export async function loadSlides(sb: SupabaseClient): Promise<SlidesState> {
  const deck = await loadDeck(sb);
  const { data: ruleRows } = await sb
    .from("owner_decisions")
    .select("action,target_id,payload,decided_at")
    .eq("surface", "slide_rule")
    .order("decided_at", { ascending: false })
    .limit(500);
  const rows = (ruleRows || []).map((r) => ({
    action: String(r.action),
    target_id: String(r.target_id),
    payload: (r.payload || {}) as Record<string, unknown>,
    decided_at: String(r.decided_at || ""),
  }));
  let planned: SlidesState["planned"] = null;
  if (deck) {
    const { data: p } = await sb
      .from("owner_decisions")
      .select("payload,decided_at")
      .eq("surface", "slide_plan")
      .eq("target_id", deck.id)
      .order("decided_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (p) {
      const pl = (p.payload || {}) as Record<string, unknown>;
      planned = {
        plan: pl.plan ? String(pl.plan) : null,
        axes: (pl.axes || {}) as Record<string, string>,
        at: String(p.decided_at || ""),
      };
    }
  }
  return { deck, rules: adoptedSlideRules(rows), decided: deck ? decidedProposals(rows, deck.id) : {}, planned };
}
