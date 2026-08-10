import { createClient } from "@/lib/supabase/server";
import type { NavCounts } from "@/lib/navBadges";
import {
  buildWatchAckFingerprint,
  isWatchAckActive,
  shouldShowWatchBadge,
} from "@/lib/watchUserAck";

export type { NavCounts };

/** サイドバーバッジ用。失敗時は 0（ナビ自体は止めない） */
export async function fetchNavCounts(): Promise<NavCounts> {
  try {
    const supabase = await createClient();
    const [partner, other, watchRows, openchat] = await Promise.all([
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
        .select("id,level,summary,status,payload")
        .eq("status", "active")
        .eq("level", "attention"),
      supabase
        .from("watch_status")
        .select("id,payload,level,summary,status")
        .eq("id", "openchat_threads")
        .eq("status", "active")
        .maybeSingle(),
    ]);

    const watchAttention = (watchRows.data || []).filter((w) =>
      shouldShowWatchBadge({
        id: w.id,
        level: w.level,
        summary: w.summary,
        status: w.status,
        payload:
          w.payload && typeof w.payload === "object"
            ? (w.payload as Record<string, unknown>)
            : null,
      }),
    ).length;

    let openchatAttention = 0;
    if (openchat.data?.level === "attention") {
      const payload =
        openchat.data.payload && typeof openchat.data.payload === "object"
          ? (openchat.data.payload as Record<string, unknown>)
          : null;
      const row = {
        id: "openchat_threads",
        level: openchat.data.level,
        summary: openchat.data.summary,
        status: openchat.data.status || "active",
        payload,
      };
      const fp = buildWatchAckFingerprint(row);
      if (!isWatchAckActive(payload, fp)) {
        const n = payload?.attention_count;
        openchatAttention =
          typeof n === "number" && n > 0 ? n : 1;
      }
    }
    return {
      partnerUnread: partner.count ?? 0,
      otherUnread: other.count ?? 0,
      watchAttention,
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
