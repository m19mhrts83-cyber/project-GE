"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { parseAdvisoryFee } from "@/lib/forceMonthly";

export type AdvisoryExtraResult = { ok: boolean; error?: string };

/** /policy の「改修対応などの追加費用」を月ごとに保存する（空なら消す）。ログイン必須・外には何も届かない */
export async function saveAdvisoryExtra(ym: string, yenText: string): Promise<AdvisoryExtraResult> {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(ym)) return { ok: false, error: "月の形式が違います" };
  const t = yenText.replace(/[,\s円¥]/g, "").trim();
  if (t !== "" && !/^\d{1,9}$/.test(t)) return { ok: false, error: "金額は数字だけで入れてください" };
  const supabase = await createClient();
  const { data: auth } = await supabase.auth.getUser();
  if (!auth?.user) return { ok: false, error: "ログインが必要です" };
  const { data: row, error: re } = await supabase
    .from("sync_meta")
    .select("value")
    .eq("key", "advisory_fee")
    .maybeSingle();
  if (re) return { ok: false, error: "読み出しに失敗しました" };
  const cur = parseAdvisoryFee(row?.value as string | undefined) || { fixed_yen: 0, fixed_from: null, extras: {} };
  if (t === "") delete cur.extras[ym];
  else cur.extras[ym] = Number(t);
  const { error } = await supabase.from("sync_meta").upsert(
    { key: "advisory_fee", value: JSON.stringify(cur), updated_at: new Date().toISOString() },
    { onConflict: "key" },
  );
  if (error) return { ok: false, error: "保存に失敗しました" };
  revalidatePath("/policy");
  return { ok: true };
}
