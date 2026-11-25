import type { SupabaseClient } from "@supabase/supabase-js";
import { CLOSE_LEAK_KEY, parseCloseLeak, pendingCards, type CloseLeakCard, type CloseLeakSnapshot } from "./closeLeak";

/**
 * 閉じ漏れの材料を読み、材料を作った後に判断済みの件を外して返す。
 * 材料がまだ一度も置かれていない／読めないときは snapshot=null（画面は「まだ届いていない」、バッジは —）。
 */
export async function loadCloseLeak(
  sb: SupabaseClient,
): Promise<{ snapshot: CloseLeakSnapshot | null; cards: CloseLeakCard[] }> {
  const { data, error } = await sb.from("sync_meta").select("value").eq("key", CLOSE_LEAK_KEY).maybeSingle();
  if (error) throw new Error(error.message);
  const snapshot = parseCloseLeak(data?.value ?? null);
  if (!snapshot) return { snapshot: null, cards: [] };
  const ids = snapshot.cards.map((c) => c.id).filter(Boolean);
  if (!ids.length) return { snapshot, cards: [] };
  const { data: rows, error: e2 } = await sb
    .from("owner_decisions")
    .select("target_id")
    .eq("surface", "todoist_313")
    .eq("target_type", "todoist_task")
    .in("action", ["close", "drop", "defer"])
    .in("target_id", ids)
    .gte("decided_at", snapshot.generated_at)
    .limit(500);
  if (e2) throw new Error(e2.message);
  return { snapshot, cards: pendingCards(snapshot, (rows || []).map((r) => String(r.target_id))) };
}
