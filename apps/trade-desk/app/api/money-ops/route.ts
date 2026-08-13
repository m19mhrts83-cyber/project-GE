import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { writeCardDebitLifecycle } from "@/lib/cardDebitLifecycle";
import { buildCardSettlementAssistSteps } from "@/lib/cardSettlementBuffer";

const KINDS = new Set([
  "bank_transfer",
  "broker_transfer",
  "securities_cash",
  "insurance_alloc",
  "card_settlement_buffer",
]);

const STATUSES = new Set([
  "draft",
  "consulting",
  "approved",
  "executing",
  "done",
  "cancelled",
]);

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const title = String(body.title || "").trim();
  const kind = String(body.kind || "bank_transfer");
  if (!title) {
    return NextResponse.json({ error: "title required" }, { status: 400 });
  }
  if (!KINDS.has(kind)) {
    return NextResponse.json({ error: "invalid kind" }, { status: 400 });
  }

  const amount =
    body.amount_jpy == null || body.amount_jpy === ""
      ? null
      : Number(body.amount_jpy);

  const statusRaw = String(body.status || "draft");
  const status = STATUSES.has(statusRaw) ? statusRaw : "draft";
  const assistIn =
    body.assist_payload && typeof body.assist_payload === "object"
      ? (body.assist_payload as Record<string, unknown>)
      : null;
  const dueDate = String(
    body.due_date || (assistIn && assistIn.due_date) || ""
  ).trim();

  if (kind === "card_settlement_buffer" && status === "consulting" && !dueDate) {
    return NextResponse.json(
      { error: "カード引落バッファの検討案には引落日が必要です" },
      { status: 400 }
    );
  }

  // 同じ引落日の open 案があれば再利用（二重作成防止）
  if (kind === "card_settlement_buffer" && dueDate) {
    const { data: existing } = await supabase
      .from("kurashift_money_ops")
      .select("id, title, status, kind")
      .eq("kind", "card_settlement_buffer")
      .in("status", ["draft", "consulting", "approved", "executing"])
      .contains("assist_payload", { due_date: dueDate })
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (existing) {
      return NextResponse.json({ ok: true, op: existing, reused: true });
    }
  }

  let assist =
    body.assist_payload && typeof body.assist_payload === "object"
      ? { ...(body.assist_payload as Record<string, unknown>) }
      : null;
  if (!assist) {
    assist = {
      steps:
        kind === "card_settlement_buffer"
          ? buildCardSettlementAssistSteps({
              dueDate: dueDate || undefined,
              needYen: amount,
            })
          : [
              "承認後に手順アシストを確認",
              "銀行／証券の振込確定は手動（自動振込なし）",
              "保険配分変更はアシストのみ",
            ],
    };
  }
  if (dueDate && !(assist as { due_date?: string }).due_date) {
    (assist as { due_date: string }).due_date = dueDate;
  }

  const { data, error } = await supabase
    .from("kurashift_money_ops")
    .insert({
      title,
      kind,
      rationale: String(body.rationale || ""),
      from_account: body.from_account ? String(body.from_account) : null,
      to_account: body.to_account ? String(body.to_account) : null,
      amount_jpy: Number.isFinite(amount as number) ? amount : null,
      status,
      assist_payload: assist,
    })
    .select("id, title, status, kind")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  if (
    kind === "card_settlement_buffer" &&
    dueDate &&
    (status === "consulting" ||
      status === "approved" ||
      status === "executing" ||
      status === "done")
  ) {
    await writeCardDebitLifecycle(supabase, {
      dueDate,
      planReady: status !== "done",
      settled: status === "done",
      opId: data.id,
    });
  }

  return NextResponse.json({ ok: true, op: data, reused: false });
}
