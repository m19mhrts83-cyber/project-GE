/** Append Jarvis lane action to Supabase (flushed to OneDrive MD on Mac). */
import { createClient } from "@/lib/supabase/server";

export async function queueLaneActionLog(input: {
  lane: string;
  event: string;
  body: string;
  cardId?: string | null;
}): Promise<void> {
  const lane = (input.lane || "").trim();
  if (!lane) return;
  try {
    const supabase = await createClient();
    await supabase.from("lane_action_log").insert({
      lane,
      event: input.event.slice(0, 80),
      body: input.body.slice(0, 4000),
      card_id: input.cardId || null,
    });
  } catch {
    /* best-effort */
  }
}
