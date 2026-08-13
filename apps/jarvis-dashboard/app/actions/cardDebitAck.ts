"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "card_debit_watch";

export type CardDebitAckResult = { ok: boolean; error?: string; message?: string };

/** 当該引落日のホームピンだけ消す（支払い義務は settled まで残る） */
export async function acknowledgeCardDebitDue(
  dueDate: string,
): Promise<CardDebitAckResult> {
  const due = (dueDate || "").trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) {
    return { ok: false, error: "引落日が不正です" };
  }

  const supabase = await createClient();
  const { data: row, error: fetchErr } = await supabase
    .from("watch_status")
    .select("id,payload,summary,detail,level")
    .eq("id", WATCH_ID)
    .maybeSingle();

  if (fetchErr) return { ok: false, error: fetchErr.message };
  if (!row) return { ok: false, error: "ウォッチが見つかりません" };

  const prev =
    row.payload && typeof row.payload === "object"
      ? ({ ...(row.payload as Record<string, unknown>) } as Record<
          string,
          unknown
        >)
      : {};

  const payload = {
    ...prev,
    dashboard_ack_due: due,
    show_banner: false,
    pin_home_top: false,
  };

  const now = new Date().toISOString();
  const { error } = await supabase
    .from("watch_status")
    .update({
      payload,
      updated_at: now,
    })
    .eq("id", WATCH_ID);
  if (error) return { ok: false, error: error.message };

  // Mac runner 合流用
  try {
    const { data: lcRow } = await supabase
      .from("sync_meta")
      .select("value")
      .eq("key", "card_debit_lifecycle")
      .maybeSingle();
    let prevLc: Record<string, unknown> = {};
    if (lcRow?.value) {
      try {
        const p = JSON.parse(String(lcRow.value));
        if (p && typeof p === "object") prevLc = p;
      } catch {
        prevLc = {};
      }
    }
    await supabase.from("sync_meta").upsert(
      {
        key: "card_debit_lifecycle",
        value: JSON.stringify({
          ...prevLc,
          dashboard_ack_due: due,
          updated_at: now,
        }),
        updated_at: now,
      },
      { onConflict: "key" },
    );
  } catch {
    /* sync_meta は任意 */
  }

  revalidatePath("/");
  revalidatePath("/situation");
  return {
    ok: true,
    message: `${due} のホーム通知を確認済（支払い完了は KURASHIFT で done）`,
  };
}
