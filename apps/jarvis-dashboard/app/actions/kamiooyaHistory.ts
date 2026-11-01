"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { appendWorkEntry, parseWorkHistory, type WorkEntryInput } from "@/lib/kamiooyaWorkHistory";

export type HistorySaveResult = { ok: boolean; message: string; savedId?: string };

export async function saveKamiooyaHistory(_previous: HistorySaveResult, form: FormData): Promise<HistorySaveResult> {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return { ok: false, message: "ログインし直してください。記録は保存されていません。" };
  const fields = ["projectId", "itemId", "eventId", "summary", "minutes", "timeKind", "workDate", "evidence", "supersedes", "questionId", "status", "correctionReason"] as const;
  const input = Object.fromEntries(fields.map(key => [key, String(form.get(key) ?? "")])) as WorkEntryInput;
  try {
    for (let attempt = 0; attempt < 4; attempt++) {
      const { data, error } = await supabase.from("sync_meta").select("value,updated_at").eq("key", "kamiooya_work_history").maybeSingle();
      if (error) throw new Error("最新の履歴を取得できませんでした。時間を置いて再試行してください。");
      const history = parseWorkHistory(data?.value);
      if (!history || typeof data?.value !== "string") throw new Error("履歴が未登録です。先にエージェントで案件を設定してください。");
      const next = appendWorkEntry(history, input);
      // 読取時の版がまだ同じ場合だけ更新。本文はURLへ含めない。
      const revision = new Date(Math.max(Date.now(), Date.parse(data.updated_at) + 1)).toISOString();
      const { data: saved, error: saveError } = await supabase.from("sync_meta")
        .update({ value: JSON.stringify(next), updated_at: revision })
        .eq("key", "kamiooya_work_history").eq("updated_at", data.updated_at).select("key");
      if (saveError) throw new Error("保存できませんでした。入力を確認して再試行してください。");
      if (saved?.length) {
        revalidatePath("/kamiooya/history");
        return { ok: true, message: "保存しました。履歴と集計を更新しました。", savedId: input.eventId };
      }
    }
    throw new Error("他の操作と更新が重なりました。入力内容を控え、再読み込みして再試行してください。");
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : "保存できませんでした。" };
  }
}
