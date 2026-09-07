"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { queueLaneActionLog } from "@/lib/laneActionLog";
import {
  isValidZaimCategory,
  type ZaimCategoryReviewItem,
  type ZaimPendingCategoryApply,
} from "@/lib/zaimCategoryCatalog";

const WATCH_ID = "zaim_quality";

export type FixConfirmResult = { ok: boolean; error?: string };

export type ZaimFixStatus = "confirmed" | "disputed" | "pending_confirm";

export type ApplyZaimCategoryInput = {
  rowKey: string;
  category: string;
  genre?: string;
  source: "category_review" | "recent_fix";
  fixId?: string;
  item: ZaimCategoryReviewItem;
};

function pendingApplyId(rowKey: string, category: string): string {
  return `dash|${rowKey}|${category}`.slice(0, 180);
}

function buildFixProposal(
  shop: string,
  amount: number | undefined,
  fromCat: string,
  toCat: string,
  genre: string,
): string {
  const yen =
    amount != null && !Number.isNaN(amount)
      ? ` ¥${Math.round(amount).toLocaleString("ja-JP")}`
      : "";
  const gen = genre ? ` / ${genre}` : "";
  return `${shop || "—"}${yen}: ${fromCat || "?"} → ${toCat}${gen}`;
}

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

/**
 * ダッシュボードから費目を選択して Zaim 反映キューへ載せる。
 * Mac の jarvis_zaim_dashboard_apply.py が Playwright 適用＋学習を行う。
 */
export async function applyZaimCategory(
  input: ApplyZaimCategoryInput,
  path = "/zaim",
): Promise<FixConfirmResult> {
  const rowKey = (input.rowKey || "").trim();
  const category = (input.category || "").trim();
  const genre = (input.genre || "").trim();
  const source = input.source;
  const item = input.item || {};

  if (!rowKey) return { ok: false, error: "row_key が空です" };
  if (!category || !isValidZaimCategory(category)) {
    return { ok: false, error: "費目が不正です" };
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

  const now = new Date().toISOString();
  const applyId = pendingApplyId(rowKey, category);
  const pending = Array.isArray(payload.pending_category_applies)
    ? ([...(payload.pending_category_applies as ZaimPendingCategoryApply[])] as ZaimPendingCategoryApply[])
    : [];

  const dup = pending.some(
    (p) =>
      p.row_key === rowKey &&
      (p.status === "queued" || p.status === "applying"),
  );
  if (dup) {
    return { ok: false, error: "同じ明細はすでに反映待ちです" };
  }

  const entry: ZaimPendingCategoryApply = {
    id: applyId,
    row_key: rowKey,
    status: "queued",
    category,
    genre,
    date: item.date,
    shop: item.shop,
    item: item.item,
    amount: item.amount,
    learn_key: item.learn_key,
    pay: item.pay,
    method: item.method || "payment",
    category_before: item.category,
    source,
    queued_at: now,
  };
  pending.push(entry);
  payload.pending_category_applies = pending.slice(-50);

  const batchId = String(payload.review_batch_id || "").trim();
  const fromCat = String(item.category || "—");
  const proposal = buildFixProposal(
    String(item.shop || ""),
    item.amount,
    fromCat,
    category,
    genre,
  );

  const fixes = Array.isArray(payload.recent_fixes)
    ? [...(payload.recent_fixes as Record<string, unknown>[])]
    : [];
  const fixRow: Record<string, unknown> = {
    id: input.fixId || applyId,
    date: item.date,
    shop: item.shop,
    amount: item.amount,
    learn_key: item.learn_key,
    row_key: rowKey,
    value: category,
    genre,
    target: "category",
    kind: "set_category",
    status: "pending_confirm",
    proposal,
    applied_at: now,
    ok: false,
    message: "dashboard_queued",
    source: "dashboard_apply",
  };
  if (batchId) stampBatchId(fixRow, batchId);
  const fixIdx = fixes.findIndex((f) => String(f.id || "") === String(fixRow.id));
  if (fixIdx >= 0) fixes[fixIdx] = { ...fixes[fixIdx], ...fixRow };
  else fixes.push(fixRow);
  payload.recent_fixes = fixes.slice(-40);

  const reviews = Array.isArray(payload.category_reviews)
    ? ([...(payload.category_reviews as ZaimCategoryReviewItem[])] as ZaimCategoryReviewItem[])
    : [];
  payload.category_reviews = reviews.map((r) => {
    if (String(r.row_key || "") !== rowKey) return r;
    return {
      ...r,
      pending_apply: true,
      pending_category: category,
      pending_genre: genre,
    };
  });

  payload.pending_confirm_count = fixes.filter((f) => {
    const st = String(f.status || "pending_confirm");
    const bid = String(f.batch_id || batchId || "");
    const ack = String(payload.dashboard_ack_batch_id || "");
    if (ack && bid && ack === bid) return false;
    return st === "pending_confirm" || st === "disputed" || !f.status;
  }).length;
  payload.show_banner = true;

  const { error: uErr } = await supabase
    .from("watch_status")
    .update({ payload, updated_at: now })
    .eq("id", WATCH_ID);
  if (uErr) return { ok: false, error: uErr.message };

  await queueLaneActionLog({
    lane: "zaim",
    event: "category_apply",
    body: JSON.stringify({
      id: applyId,
      row_key: rowKey,
      category,
      genre,
      shop: item.shop,
      date: item.date,
      amount: item.amount,
      learn_key: item.learn_key,
    }),
  });

  revalidatePath(path);
  revalidatePath("/situation");
  revalidatePath("/");
  return { ok: true };
}
