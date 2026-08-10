import { createClient } from "@/lib/supabase/server";
import type { NavCounts } from "@/lib/navBadges";

export type { NavCounts };

/** サイドバーバッジ用。失敗時は 0（ナビ自体は止めない） */
export async function fetchNavCounts(): Promise<NavCounts> {
  try {
    const supabase = await createClient();
    const [partner, other, watch, openchat] = await Promise.all([
      supabase
        .from("triage_items")
        .select("id", { count: "exact", head: true })
        .eq("lane", "partner")
        .eq("status", "pending")
        .neq("kind", "activity"),
      supabase
        .from("triage_items")
        .select("id", { count: "exact", head: true })
        .neq("lane", "partner")
        .eq("status", "pending")
        .neq("kind", "activity"),
      supabase
        .from("watch_status")
        .select("id", { count: "exact", head: true })
        .eq("status", "active")
        .eq("level", "attention"),
      supabase
        .from("watch_status")
        .select("id,payload,level")
        .eq("id", "openchat_threads")
        .eq("status", "active")
        .maybeSingle(),
    ]);
    let openchatAttention = 0;
    if (openchat.data?.level === "attention") {
      const payload = openchat.data.payload;
      if (payload && typeof payload === "object") {
        const n = (payload as { attention_count?: unknown }).attention_count;
        openchatAttention =
          typeof n === "number" && n > 0 ? n : 1;
      } else {
        openchatAttention = 1;
      }
    }
    return {
      partnerUnread: partner.count ?? 0,
      otherUnread: other.count ?? 0,
      watchAttention: watch.count ?? 0,
      openchatAttention,
    };
  } catch {
    return {
      partnerUnread: 0,
      otherUnread: 0,
      watchAttention: 0,
      openchatAttention: 0,
    };
  }
}
