import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { writeCardDebitLifecycle } from "@/lib/cardDebitLifecycle";

const ALLOWED: Record<string, string[]> = {
  draft: ["consulting", "approved", "cancelled"],
  consulting: ["draft", "approved", "cancelled"],
  approved: ["executing", "consulting", "cancelled"],
  executing: ["done", "cancelled"],
  done: ["cancelled"],
  cancelled: ["draft"],
};

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
  const next = String(body.status || "");
  if (!next) {
    return NextResponse.json({ error: "status required" }, { status: 400 });
  }

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

  const allowed = ALLOWED[row.status] || [];
  if (!allowed.includes(next)) {
    return NextResponse.json(
      { error: `遷移不可: ${row.status} → ${next}`, allowed },
      { status: 400 }
    );
  }

  const prevAssist =
    row.assist_payload && typeof row.assist_payload === "object"
      ? { ...(row.assist_payload as Record<string, unknown>) }
      : {};

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
