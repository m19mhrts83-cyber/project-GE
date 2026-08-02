"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "rent_step";

export type RentStepAckResult = { ok: boolean; error?: string };

/** 家賃ステップ確認済みにしてバナーを消す（当該 target_month のみ） */
export async function acknowledgeRentStep(
  targetMonth: string,
): Promise<RentStepAckResult> {
  const ym = (targetMonth || "").trim();
  if (!/^\d{4}-\d{2}$/.test(ym)) {
    return { ok: false, error: "対象月が不正です" };
  }

  const supabase = await createClient();
  const { data: row, error: fetchErr } = await supabase
    .from("watch_status")
    .select("id,payload,summary,detail,level")
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

  const payload = {
    ...prev,
    dashboard_ack_target_month: ym,
    show_banner: false,
  };

  const summary = `${ym}分 確認済 · 次は翌月更新後`;
  const now = new Date().toISOString();

  if (!row) {
    const { error } = await supabase.from("watch_status").upsert(
      {
        id: WATCH_ID,
        title: "Grandole家賃ステップ（+4,000）",
        category: "finance",
        level: "ok",
        summary,
        detail: "ダッシュボードで確認済み",
        status: "active",
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
        updated_at: now,
      })
      .eq("id", WATCH_ID);
    if (error) return { ok: false, error: error.message };
  }

  revalidatePath("/rent-step");
  revalidatePath("/situation");
  revalidatePath("/");
  return { ok: true };
}
