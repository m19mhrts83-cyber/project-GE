"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "card_debit_watch";

export type CardDebitSettleResult = {
  ok: boolean;
  error?: string;
  message?: string;
};

/**
 * 寄せ完了（資金移動済み）として当該引落日のウォッチを消す。
 * 引落そのものの完了ではない。money-ops があれば done に揃える。
 */
export async function settleCardDebitFundMove(
  dueDate: string,
): Promise<CardDebitSettleResult> {
  const due = (dueDate || "").trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) {
    return { ok: false, error: "引落日が不正です" };
  }

  const supabase = await createClient();
  const now = new Date().toISOString();

  // 1) lifecycle（Mac runner 合流）
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
  const nextLc: Record<string, unknown> = {
    ...prevLc,
    settled_due: due,
    dashboard_ack_due: due,
    updated_at: now,
  };
  if (String(nextLc.plan_ready_due || "") === due) {
    nextLc.plan_ready_due = null;
  }
  const { error: lcErr } = await supabase.from("sync_meta").upsert(
    {
      key: "card_debit_lifecycle",
      value: JSON.stringify(nextLc),
      updated_at: now,
    },
    { onConflict: "key" },
  );
  if (lcErr) return { ok: false, error: lcErr.message };

  // 2) 当該 due の money-ops を done に
  const { data: ops } = await supabase
    .from("kurashift_money_ops")
    .select("id, status, assist_payload")
    .eq("kind", "card_settlement_buffer")
    .in("status", ["consulting", "approved", "executing"])
    .order("updated_at", { ascending: false })
    .limit(20);

  let closed = 0;
  for (const op of ops || []) {
    const ap =
      op.assist_payload && typeof op.assist_payload === "object"
        ? ({ ...(op.assist_payload as Record<string, unknown>) } as Record<
            string,
            unknown
          >)
        : {};
    const opDue = String(ap.due_date || "").trim().slice(0, 10);
    if (opDue !== due) continue;
    ap.settled_due = due;
    ap.settled_at = now;
    if (String(ap.plan_ready_due || "") === due) {
      delete ap.plan_ready_due;
    }
    const rails = Array.isArray(ap.rails) ? [...(ap.rails as unknown[])] : [];
    ap.rails = rails.map((r) => {
      if (!r || typeof r !== "object") return r;
      const cur = { ...(r as Record<string, unknown>) };
      const st = String(cur.status || "");
      if (st !== "done" && st !== "cancelled") {
        cur.status = "done";
        cur.updated_at = now;
        if (!cur.note) cur.note = "ダッシュボード寄せ完了で一括 done";
      }
      return cur;
    });
    const { error } = await supabase
      .from("kurashift_money_ops")
      .update({
        status: "done",
        assist_payload: ap,
        updated_at: now,
      })
      .eq("id", op.id);
    if (!error) {
      closed += 1;
      nextLc.source_op_id = op.id;
    }
  }
  if (closed > 0) {
    await supabase.from("sync_meta").upsert(
      {
        key: "card_debit_lifecycle",
        value: JSON.stringify({ ...nextLc, updated_at: now }),
        updated_at: now,
      },
      { onConflict: "key" },
    );
  }

  // 3) watch_status をピン解除＋寄せ完了メモ
  const { data: row } = await supabase
    .from("watch_status")
    .select("id,payload,summary")
    .eq("id", WATCH_ID)
    .maybeSingle();
  if (row) {
    const prev =
      row.payload && typeof row.payload === "object"
        ? ({ ...(row.payload as Record<string, unknown>) } as Record<
            string,
            unknown
          >)
        : {};
    const payload = {
      ...prev,
      settled_due: due,
      dashboard_ack_due: due,
      show_banner: false,
      pin_home_top: false,
      fund_move_settled_at: now,
    };
    await supabase
      .from("watch_status")
      .update({
        payload,
        level: "ok",
        summary: `${due} 寄せ完了（引落待機）`,
        updated_at: now,
      })
      .eq("id", WATCH_ID);
  }

  revalidatePath("/");
  revalidatePath("/situation");
  return {
    ok: true,
    message:
      closed > 0
        ? `${due} 寄せ完了（money-ops ${closed}件を done）`
        : `${due} 寄せ完了（ウォッチ解除）`,
  };
}
