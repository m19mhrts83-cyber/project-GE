"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "ops_fix_notice";

export type OpsFixAckResult = { ok: boolean; error?: string };

/** 「Jarvisが直したよ」を確認済みにしてホーム／詳細から消す（アーカイブしない） */
export async function acknowledgeOpsFixNotice(): Promise<OpsFixAckResult> {
  const supabase = await createClient();
  const { data: row, error: fetchErr } = await supabase
    .from("watch_status")
    .select("id,payload,summary,title")
    .eq("id", WATCH_ID)
    .maybeSingle();

  if (fetchErr) return { ok: false, error: fetchErr.message };

  const prev =
    row?.payload && typeof row.payload === "object"
      ? ({ ...(row.payload as Record<string, unknown>) } as Record<
          string,
          unknown
        >)
      : {};

  const note = String(prev.note || row?.summary || "").trim();
  const now = new Date().toISOString();
  const payload = {
    ...prev,
    show_banner: false,
    never_archive: true,
    ephemeral: true,
    origin: prev.origin || "ops_fail_watch",
    acknowledged_at: now,
  };

  const summary = note
    ? `確認済み · ${note}`.slice(0, 500)
    : "確認済み（直近の修正お知らせ）";

  if (!row) {
    const { error } = await supabase.from("watch_status").upsert(
      {
        id: WATCH_ID,
        title: "Jarvisが直したよ",
        category: "ops",
        level: "ok",
        summary,
        detail: null,
        status: "active",
        archived_at: null,
        payload,
        checked_at: now,
        updated_at: now,
      },
      { onConflict: "id" },
    );
    if (error) return { ok: false, error: error.message };
  } else {
    const { error } = await supabase
      .from("watch_status")
      .update({
        payload,
        summary,
        level: "ok",
        status: "active",
        archived_at: null,
        updated_at: now,
      })
      .eq("id", WATCH_ID);
    if (error) return { ok: false, error: error.message };
  }

  revalidatePath("/");
  revalidatePath("/situation");
  revalidatePath("/queue");
  return { ok: true };
}
