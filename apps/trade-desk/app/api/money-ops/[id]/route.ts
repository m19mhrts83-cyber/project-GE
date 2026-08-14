import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { writeCardDebitLifecycle } from "@/lib/cardDebitLifecycle";
import type { TransferRailStatus } from "@/lib/cardSettlementBuffer";

const ALLOWED: Record<string, string[]> = {
  draft: ["consulting", "approved", "cancelled"],
  consulting: ["draft", "approved", "cancelled"],
  approved: ["executing", "consulting", "cancelled"],
  executing: ["done", "cancelled"],
  done: ["cancelled"],
  cancelled: ["draft"],
};

const RAIL_STATUSES = new Set<TransferRailStatus>([
  "pending",
  "previewed",
  "running",
  "awaiting_final_confirm",
  "otp_fetch",
  "otp_submit",
  "waiting_user",
  "executing_click",
  "verifying",
  "done",
  "failed",
  "blocked",
  "deferred",
]);

export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const railId = typeof body.rail_id === "string" ? body.rail_id.trim() : "";
  const railStatus =
    typeof body.rail_status === "string" ? body.rail_status.trim() : "";
  const next = String(body.status || "");

  const { data: row, error: getErr } = await supabase
    .from("kurashift_money_ops")
    .select("id, status, title, kind, assist_payload")
    .eq("id", id)
    .maybeSingle();
  if (getErr || !row) {
    return NextResponse.json(
      { error: getErr?.message || "not found" },
      { status: 404 }
    );
  }

  const prevAssist =
    row.assist_payload && typeof row.assist_payload === "object"
      ? { ...(row.assist_payload as Record<string, unknown>) }
      : {};

  // レール単位の更新（オペ status は任意）
  if (railId && railStatus) {
    if (!RAIL_STATUSES.has(railStatus as TransferRailStatus)) {
      return NextResponse.json(
        { error: `不正な rail_status: ${railStatus}` },
        { status: 400 }
      );
    }
    const railsRaw = Array.isArray(prevAssist.rails) ? [...prevAssist.rails] : [];
    const idx = railsRaw.findIndex(
      (r) =>
        r &&
        typeof r === "object" &&
        String((r as Record<string, unknown>).id || "") === railId
    );
    if (idx < 0) {
      return NextResponse.json(
        { error: `rail not found: ${railId}` },
        { status: 404 }
      );
    }
    const cur = { ...(railsRaw[idx] as Record<string, unknown>) };
    cur.status = railStatus;
    cur.updated_at = new Date().toISOString();
    if (typeof body.note === "string" && body.note.trim()) {
      cur.note = body.note.trim().slice(0, 400);
    }
    if (typeof body.evidence === "string") {
      cur.evidence = body.evidence.slice(0, 500);
    }
    if (typeof body.last_error === "string") {
      cur.last_error = body.last_error.slice(0, 400);
    }
    if (typeof body.remind_at === "string") {
      cur.remind_at = body.remind_at.slice(0, 80);
    }
    railsRaw[idx] = cur;
    const assistNext = {
      ...prevAssist,
      rails: railsRaw,
      rail_updated_at: new Date().toISOString(),
      execution_ux: prevAssist.execution_ux || {
        model: "plan_approve→jarvis_execute→final_confirm→otp_submit",
        user_only: ["plan_approve", "final_confirm", "otp_submit"],
      },
    };
    const patch: Record<string, unknown> = {
      assist_payload: assistNext,
      updated_at: new Date().toISOString(),
    };
    if (next && (ALLOWED[row.status] || []).includes(next)) {
      patch.status = next;
    }
    const { data, error } = await supabase
      .from("kurashift_money_ops")
      .update(patch)
      .eq("id", id)
      .select("id, title, status, kind, assist_payload")
      .single();
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }
    return NextResponse.json({ ok: true, op: data, rail: cur });
  }

  if (!next) {
    return NextResponse.json(
      { error: "status or rail_id+rail_status required" },
      { status: 400 }
    );
  }

  const allowed = ALLOWED[row.status] || [];
  if (!allowed.includes(next)) {
    return NextResponse.json(
      { error: `遷移不可: ${row.status} → ${next}`, allowed },
      { status: 400 }
    );
  }

  const patch: Record<string, unknown> = {
    status: next,
    updated_at: new Date().toISOString(),
  };

  if (next === "approved") {
    patch.assist_payload = {
      ...prevAssist,
      approved_at: new Date().toISOString(),
      approved_by: user.email ?? user.id,
      auto_execute: false,
      execution_ux: {
        model: "plan_approve→jarvis_execute→final_confirm→otp_submit",
        user_only: ["plan_approve", "final_confirm", "otp_submit"],
      },
    };
  }

  if (row.kind === "card_settlement_buffer") {
    const due = String(prevAssist.due_date || "").trim().slice(0, 10);
    const assistNext = {
      ...((patch.assist_payload as Record<string, unknown>) || prevAssist),
    };
    if (next === "done" && due) {
      assistNext.settled_due = due;
      assistNext.settled_at = new Date().toISOString();
      patch.assist_payload = assistNext;
    } else if (
      (next === "consulting" || next === "approved" || next === "executing") &&
      due
    ) {
      assistNext.plan_ready_due = due;
      patch.assist_payload = assistNext;
    }
  }

  const { data, error } = await supabase
    .from("kurashift_money_ops")
    .update(patch)
    .eq("id", id)
    .select("id, title, status, kind, assist_payload")
    .single();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  if (row.kind === "card_settlement_buffer") {
    const ap =
      data.assist_payload && typeof data.assist_payload === "object"
        ? (data.assist_payload as Record<string, unknown>)
        : prevAssist;
    const due = String(ap.due_date || "").trim().slice(0, 10);
    if (due) {
      await writeCardDebitLifecycle(supabase, {
        dueDate: due,
        planReady:
          next === "consulting" || next === "approved" || next === "executing",
        settled: next === "done",
        opId: id,
      });
    }
  }

  return NextResponse.json({ ok: true, op: data });
}
