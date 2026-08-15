import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

const LINES = new Set(["realestate", "ai"]);
const ENTITIES = new Set(["personal", "corporate"]);
const SCENARIOS = new Set(["actual", "plan"]);
const SOURCES = new Set(["manual", "jarvis", "import"]);

function numOrNull(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function numOrZero(v: unknown): number {
  const n = numOrNull(v);
  return n ?? 0;
}

/** YYYY-MM or YYYY-MM-DD → 月初 date */
function toPeriodMonth(raw: unknown): string | null {
  const s = String(raw || "").trim();
  if (/^\d{4}-\d{2}$/.test(s)) return `${s}-01`;
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return `${s.slice(0, 7)}-01`;
  return null;
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
  let q = supabase
    .from("kurashift_mq_period_facts")
    .select("*")
    .eq("scenario_kind", "actual")
    .order("period_month", { ascending: false });

  const line = url.searchParams.get("business_line");
  if (line && LINES.has(line)) q = q.eq("business_line", line);
  const entity = url.searchParams.get("entity");
  if (entity && ENTITIES.has(entity)) q = q.eq("entity", entity);

  const { data, error } = await q.limit(200);
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
  const business_line = String(body.business_line || "");
  const entity = String(body.entity || "");
  const period_month = toPeriodMonth(body.period_month);
  const scenario_kind = String(body.scenario_kind || "actual");
  const plan_variant_id = String(body.plan_variant_id || "");
  const source = String(body.source || "manual");

  if (!LINES.has(business_line)) {
    return NextResponse.json(
      { error: "business_line must be realestate|ai" },
      { status: 400 }
    );
  }
  if (!ENTITIES.has(entity)) {
    return NextResponse.json(
      { error: "entity must be personal|corporate" },
      { status: 400 }
    );
  }
  if (!period_month) {
    return NextResponse.json(
      { error: "period_month must be YYYY-MM" },
      { status: 400 }
    );
  }
  if (!SCENARIOS.has(scenario_kind)) {
    return NextResponse.json({ error: "scenario_kind invalid" }, { status: 400 });
  }
  if (!SOURCES.has(source)) {
    return NextResponse.json({ error: "source invalid" }, { status: 400 });
  }

  const row = {
    business_line,
    entity,
    period_month,
    scenario_kind,
    plan_variant_id,
    q: numOrNull(body.q),
    pq: numOrZero(body.pq),
    vq: numOrZero(body.vq),
    f: numOrZero(body.f),
    f_annual: numOrZero(body.f_annual),
    cash_in: numOrNull(body.cash_in),
    cash_out: numOrNull(body.cash_out),
    cash_end: numOrNull(body.cash_end),
    depreciation_jpy: numOrNull(body.depreciation_jpy),
    note: body.note ? String(body.note).slice(0, 2000) : null,
    source,
    updated_at: new Date().toISOString(),
  };

  const { data, error } = await supabase
    .from("kurashift_mq_period_facts")
    .upsert(row, {
      onConflict:
        "business_line,entity,period_month,scenario_kind,plan_variant_id",
    })
    .select("*")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, row: data });
}
