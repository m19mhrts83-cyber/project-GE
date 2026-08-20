import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import {
  isAdjustmentFieldKey,
} from "@/lib/mqCashflowManual";

const LINES = new Set(["realestate", "ai"]);
const ENTITIES = new Set(["personal", "corporate"]);

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

  let q = supabase.from("kurashift_mq_cashflow_adjustments").select("*");
  if (LINES.has(line)) q = q.eq("business_line", line);
  if (ENTITIES.has(entity)) q = q.eq("entity", entity);
  if (year && /^\d{4}$/.test(year)) {
    q = q
      .gte("period_month", `${year}-01-01`)
      .lt("period_month", `${Number(year) + 1}-01-01`);
  }

  const { data, error } = await q.order("period_month", { ascending: true });
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, rows: data ?? [] });
}

export async function PUT(req: Request) {
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
  const field_key = String(body.fieldKey || body.field_key || "");
  const amount_man = num(body.amountMan ?? body.amount_man);
  const note = body.note ? String(body.note).slice(0, 500) : null;

  if (!LINES.has(business_line) || !ENTITIES.has(entity)) {
    return NextResponse.json({ error: "line/entity invalid" }, { status: 400 });
  }
  if (!period_month || !isAdjustmentFieldKey(field_key)) {
    return NextResponse.json(
      { error: "periodMonth and fieldKey required" },
      { status: 400 }
    );
  }
  if (amount_man == null) {
    return NextResponse.json({ error: "amountMan required" }, { status: 400 });
  }

  if (amount_man === 0) {
    const { error } = await supabase
      .from("kurashift_mq_cashflow_adjustments")
      .delete()
      .eq("business_line", business_line)
      .eq("entity", entity)
      .eq("period_month", period_month)
      .eq("field_key", field_key);
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }
    return NextResponse.json({ ok: true, deleted: true });
  }

  const { data, error } = await supabase
    .from("kurashift_mq_cashflow_adjustments")
    .upsert(
      {
        business_line,
        entity,
        period_month,
        field_key,
        amount_man,
        source: "manual",
        note,
        created_by: user.id,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "business_line,entity,period_month,field_key" }
    )
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
    .from("kurashift_mq_cashflow_adjustments")
    .delete()
    .eq("id", id);
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true });
}
