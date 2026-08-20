import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import type { CashflowActionKind } from "@/lib/mqCashflowManual";

const LINES = new Set(["realestate", "ai"]);
const ENTITIES = new Set(["personal", "corporate"]);
const KINDS = new Set<CashflowActionKind>([
  "officer",
  "borrow_st",
  "borrow_lt",
]);

function toPeriodMonth(raw: unknown): string | null {
  const s = String(raw || "").trim();
  if (/^\d{4}-\d{2}$/.test(s)) return `${s}-01`;
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return `${s.slice(0, 7)}-01`;
  return null;
}

function num(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export async function GET(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const url = new URL(req.url);
  const line = url.searchParams.get("line") || "realestate";
  const entity = url.searchParams.get("entity") || "corporate";
  const year = url.searchParams.get("year");

  let q = supabase.from("kurashift_mq_cashflow_actions").select("*");
  if (LINES.has(line)) q = q.eq("business_line", line);
  if (ENTITIES.has(entity)) q = q.eq("entity", entity);
  if (year && /^\d{4}$/.test(year)) {
    q = q
      .gte("period_month", `${year}-01-01`)
      .lt("period_month", `${Number(year) + 1}-01-01`);
  }

  const { data, error } = await q
    .order("period_month", { ascending: true })
    .order("sort_order", { ascending: true });
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, rows: data ?? [] });
}

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const business_line = String(body.businessLine || body.business_line || "realestate");
  const entity = String(body.entity || "corporate");
  const period_month = toPeriodMonth(body.periodMonth || body.period_month);
  const action_kind = String(body.actionKind || body.action_kind || "") as CashflowActionKind;
  const amount_man = num(body.amountMan ?? body.amount_man);
  const label = String(body.label || "").slice(0, 200);

  if (!LINES.has(business_line) || !ENTITIES.has(entity)) {
    return NextResponse.json({ error: "line/entity invalid" }, { status: 400 });
  }
  if (!period_month || !KINDS.has(action_kind)) {
    return NextResponse.json(
      { error: "periodMonth and actionKind required" },
      { status: 400 }
    );
  }
  if (amount_man == null || amount_man <= 0) {
    return NextResponse.json({ error: "amountMan must be > 0" }, { status: 400 });
  }

  const { data, error } = await supabase
    .from("kurashift_mq_cashflow_actions")
    .insert({
      business_line,
      entity,
      period_month,
      action_kind,
      amount_man,
      label,
      is_active: true,
      created_by: user.id,
    })
    .select("*")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, row: data });
}

export async function PATCH(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const id = String(body.id || "");
  if (!id) {
    return NextResponse.json({ error: "id required" }, { status: 400 });
  }

  const patch: Record<string, unknown> = {
    updated_at: new Date().toISOString(),
  };
  if (body.isActive === false || body.is_active === false) patch.is_active = false;
  if (body.isActive === true || body.is_active === true) patch.is_active = true;
  if (body.amountMan != null || body.amount_man != null) {
    const amt = num(body.amountMan ?? body.amount_man);
    if (amt == null || amt <= 0) {
      return NextResponse.json({ error: "amountMan must be > 0" }, { status: 400 });
    }
    patch.amount_man = amt;
  }
  if (body.label != null) patch.label = String(body.label).slice(0, 200);

  const { data, error } = await supabase
    .from("kurashift_mq_cashflow_actions")
    .update(patch)
    .eq("id", id)
    .select("*")
    .single();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, row: data });
}

export async function DELETE(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "id required" }, { status: 400 });
  }

  const { error } = await supabase
    .from("kurashift_mq_cashflow_actions")
    .delete()
    .eq("id", id);
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true });
}
