import { createClient } from "@/lib/supabase/server";

export type NavCounts = {
  partnerUnread: number;
  watchAttention: number;
  otherUnread: number;
};

/** サイドバーバッジ用。失敗時は 0（ナビ自体は止めない） */
export async function fetchNavCounts(): Promise<NavCounts> {
  try {
    const supabase = await createClient();
    const [partner, other, watch] = await Promise.all([
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
    ]);
    return {
      partnerUnread: partner.count ?? 0,
      otherUnread: other.count ?? 0,
      watchAttention: watch.count ?? 0,
    };
  } catch {
    return { partnerUnread: 0, otherUnread: 0, watchAttention: 0 };
  }
}

export function badgeForHref(
  href: string,
  counts: NavCounts,
): number | null {
  if (href === "/partner") return counts.partnerUnread || null;
  if (href === "/general") return counts.otherUnread || null;
  if (href === "/situation") return counts.watchAttention || null;
  return null;
}
