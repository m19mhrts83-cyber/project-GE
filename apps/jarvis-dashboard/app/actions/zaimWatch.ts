"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "zaim_quality";

export type FixConfirmResult = { ok: boolean; error?: string };

export async function confirmZaimFix(
  fixId: string,
  next: "confirmed" | "disputed",
  path = "/zaim",
  comment?: string,
): Promise<FixConfirmResult> {
  const id = fixId.trim();
  if (!id) return { ok: false, error: "id が空です" };

  const supabase = await createClient();
  const { data: watch, error } = await supabase
    .from("watch_status")
    .select("id,payload")
    .eq("id", WATCH_ID)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  if (!watch) return { ok: false, error: "Zaim Watch が未 push です" };

  const payload =
    watch.payload && typeof watch.payload === "object"
      ? ({ ...(watch.payload as Record<string, unknown>) } as Record<
          string,
          unknown
        >)
      : {};
  const fixes = Array.isArray(payload.recent_fixes)
    ? [...(payload.recent_fixes as Record<string, unknown>[])]
    : [];
  let found = false;
  for (let i = 0; i < fixes.length; i++) {
    const row = { ...fixes[i] };
    if (String(row.id || "") === id) {
      row.status = next;
      row.confirmed_at = new Date().toISOString();
      fixes[i] = row;
      found = true;
    }
  }
  if (!found) {
    fixes.push({
      id,
      status: next,
      confirmed_at: new Date().toISOString(),
      proposal: "(ダッシュボードから更新)",
    });
  }
  payload.recent_fixes = fixes;
  payload.pending_confirm_count = fixes.filter(
    (f) => f && f.status === "pending_confirm",
  ).length;

  const { error: uErr } = await supabase
    .from("watch_status")
    .update({ payload, updated_at: new Date().toISOString() })
    .eq("id", WATCH_ID);
  if (uErr) return { ok: false, error: uErr.message };

  if (next === "disputed") {
    const note = (comment || "").trim();
    await supabase.from("watch_comments").insert({
      watch_id: WATCH_ID,
      role: "user",
      body: note
        ? `直しがおかしい: ${id}\n${note.slice(0, 800)}`
        : `直しがおかしい: ${id}`,
    });
  }

  revalidatePath(path);
  revalidatePath("/situation");
  revalidatePath("/");
  return { ok: true };
}
