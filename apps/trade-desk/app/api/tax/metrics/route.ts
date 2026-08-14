import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

const SCOPES = new Set(["personal", "corporate"]);
const REFUND = new Set(["refund", "pay", "zero"]);
const FILING = new Set(["draft", "filed", "amended", "unknown"]);
const SOURCES = new Set(["manual", "jarvis", "import"]);

function numOrNull(v: unknown): number | null {
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
  const scope = url.searchParams.get("scope");
  let q = supabase
    .from("kurashift_tax_year_metrics")
    .select("*")
    .order("fiscal_year", { ascending: false });
  if (scope && SCOPES.has(scope)) {
    q = q.eq("scope", scope);
  }
  const { data, error } = await q;
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
  const scope = String(body.scope || "");
  const fiscal_year = Number(body.fiscal_year);
  if (!SCOPES.has(scope)) {
    return NextResponse.json({ error: "scope must be personal|corporate" }, { status: 400 });
  }
  if (!Number.isFinite(fiscal_year) || fiscal_year < 2000 || fiscal_year > 2100) {
    return NextResponse.json({ error: "fiscal_year invalid" }, { status: 400 });
  }

  const refund_or_pay = body.refund_or_pay
    ? String(body.refund_or_pay)
    : null;
  if (refund_or_pay && !REFUND.has(refund_or_pay)) {
    return NextResponse.json({ error: "refund_or_pay invalid" }, { status: 400 });
  }
  const filing_status = body.filing_status
    ? String(body.filing_status)
    : null;
  if (filing_status && !FILING.has(filing_status)) {
    return NextResponse.json({ error: "filing_status invalid" }, { status: 400 });
  }
  const source = String(body.source || "manual");
  if (!SOURCES.has(source)) {
    return NextResponse.json({ error: "source invalid" }, { status: 400 });
  }

  const payload =
    body.payload && typeof body.payload === "object" && !Array.isArray(body.payload)
      ? (body.payload as Record<string, unknown>)
      : undefined;

  const row: Record<string, unknown> = {
    scope,
    fiscal_year,
    filing_status,
    filed_on: body.filed_on ? String(body.filed_on).slice(0, 10) : null,
    note: body.note ? String(body.note).slice(0, 2000) : null,
    source,
    taxable_income_jpy: numOrNull(body.taxable_income_jpy),
    income_tax_jpy: numOrNull(body.income_tax_jpy),
    refund_or_pay,
    revenue_jpy: numOrNull(body.revenue_jpy),
    ordinary_income_jpy: numOrNull(body.ordinary_income_jpy),
    corporate_tax_jpy: numOrNull(body.corporate_tax_jpy),
    tax_payable_jpy: numOrNull(body.tax_payable_jpy),
    updated_at: new Date().toISOString(),
  };
  if (payload) {
    row.payload = payload;
  }

  const { data, error } = await supabase
    .from("kurashift_tax_year_metrics")
    .upsert(row, { onConflict: "scope,fiscal_year" })
    .select("*")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, row: data });
}
