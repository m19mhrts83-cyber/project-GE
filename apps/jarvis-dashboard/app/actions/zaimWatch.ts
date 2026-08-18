"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "zaim_quality";

export type FixConfirmResult = { ok: boolean; error?: string };

export type ZaimFixStatus = "confirmed" | "disputed" | "pending_confirm";

function stampBatchId(
  row: Record<string, unknown>,
  ackId: string,
): Record<string, unknown> {
  if (!String(row.batch_id || "").trim()) {
    row.batch_id = ackId;
  }
  return row;
}

export async function confirmZaimFix(
  fixId: string,
  next: ZaimFixStatus,
  path = "/zaim",
  comment?: string,
): Promise<FixConfirmResult> {
  const id = fixId.trim();
  if (!id) return { ok: false, error: "id が空です" };
  if (!["confirmed", "disputed", "pending_confirm"].includes(next)) {
    return { ok: false, error: "status が不正です" };
  }

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
  const batchId = String(payload.review_batch_id || "").trim();
  const fixes = Array.isArray(payload.recent_fixes)
    ? [...(payload.recent_fixes as Record<string, unknown>[])]
    : [];
  let found = false;
  for (let i = 0; i < fixes.length; i++) {
    const row = { ...fixes[i] };
    if (String(row.id || "") === id) {
      row.status = next;
      row.flagged_at = next === "disputed" ? new Date().toISOString() : null;
      if (batchId) stampBatchId(row, batchId);
      fixes[i] = row;
      found = true;
    }
  }
  if (!found) {
    const row: Record<string, unknown> = {
      id,
      status: next,
      flagged_at: next === "disputed" ? new Date().toISOString() : null,
      proposal: "(ダッシュボードから更新)",
    };
    if (batchId) stampBatchId(row, batchId);
    fixes.push(row);
  }
  payload.recent_fixes = fixes;
  payload.pending_confirm_count = fixes.filter((f) => {
    const st = String(f.status || "pending_confirm");
    const bid = String(f.batch_id || batchId || "");
    const ack = String(payload.dashboard_ack_batch_id || "");
    if (ack && bid && ack === bid) return false;
    return st === "pending_confirm" || st === "disputed" || !f.status;
  }).length;

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
        ? `学習が違う: ${id}\n${note.slice(0, 800)}`
        : `学習が違う: ${id}`,
    });
  }

  revalidatePath(path);
  revalidatePath("/situation");
  revalidatePath("/");
  return { ok: true };
}

/**
 * 「Jarvisが直したよ（財務）」を確認済みにしてホームピンと一覧を消す。
 * pending は confirmed。disputed（おかしいフラグ）は上書きしない。
 */
export async function acknowledgeZaimReview(
  batchId?: string,
): Promise<FixConfirmResult> {
  const supabase = await createClient();
  const { data: watch, error } = await supabase
    .from("watch_status")
    .select("id,payload,summary,level")
    .eq("id", WATCH_ID)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  if (!watch) return { ok: false, error: "Zaim Watch が未 push です" };

  const prev =
    watch.payload && typeof watch.payload === "object"
      ? ({ ...(watch.payload as Record<string, unknown>) } as Record<
          string,
          unknown
        >)
      : {};

  const now = new Date().toISOString();
  const bid = (batchId || "").trim();
  const existingBatch = String(prev.review_batch_id || "").trim();
  const pendingIds = (
    Array.isArray(prev.recent_fixes)
      ? (prev.recent_fixes as Record<string, unknown>[])
      : []
  )
    .filter((f) => {
      const st = String(f.status || "pending_confirm");
      return st === "pending_confirm" || st === "disputed" || !f.status;
    })
    .map((f) => String(f.id || ""))
    .filter(Boolean)
    .sort()
    .join(",");

  const ackId =
    bid ||
    existingBatch ||
    (pendingIds ? `pending:${pendingIds.slice(0, 120)}` : `ack:${now}`);

  const fixes = Array.isArray(prev.recent_fixes)
    ? (prev.recent_fixes as Record<string, unknown>[]).map((f) => {
        const row = stampBatchId({ ...f }, ackId);
        if (row.status === "pending_confirm" || !row.status) {
          row.status = "confirmed";
          row.confirmed_at = now;
        }
        return row;
      })
    : [];

  const note = String(watch.summary || "")
    .replace(/^見直したよ[·・]\s*/, "")
    .replace(/^直し確認待ち\s*\d+件\s*[·・]\s*/, "")
    .replace(/^Jarvisが直したよ（財務）[·・]\s*/, "")
    .slice(0, 180);

  const payload = {
    ...prev,
    recent_fixes: fixes,
    pending_confirm_count: 0,
    dashboard_ack_batch_id: ackId,
    review_batch_id: existingBatch || ackId,
    show_banner: false,
    acknowledged_at: now,
  };

  const { error: uErr } = await supabase
    .from("watch_status")
    .update({
      payload,
      level: "ok",
      title: "Zaim Watch",
      summary: note
        ? `確認済み · ${note}`.slice(0, 500)
        : "確認済み（財務の直しお知らせ）",
      updated_at: now,
    })
    .eq("id", WATCH_ID);
  if (uErr) return { ok: false, error: uErr.message };

  revalidatePath("/zaim");
  revalidatePath("/situation");
  revalidatePath("/");
  return { ok: true };
}
