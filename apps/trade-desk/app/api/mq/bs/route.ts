import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { normalizeBs } from "@/lib/mqBs";

const LINES = new Set(["realestate", "ai"]);
const ENTITIES = new Set(["personal", "corporate"]);
const SOURCES = new Set(["manual", "jarvis", "import"]);

function toAsOf(raw: unknown): string | null {
  const s = String(raw || "").trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  if (/^\d{4}-\d{2}$/.test(s)) {
    const [y, mo] = s.split("-").map(Number);
    const last = new Date(y, mo, 0).getDate();
    return `${s}-${String(last).padStart(2, "0")}`;
  }
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
    .from("kurashift_mq_bs_snapshots")
    .select("*")
    .order("as_of_date", { ascending: false });

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
  const as_of_date = toAsOf(body.as_of_date);
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
  if (!as_of_date) {
    return NextResponse.json(
      { error: "as_of_date must be YYYY-MM or YYYY-MM-DD" },
      { status: 400 }
    );
  }
  if (!SOURCES.has(source)) {
    return NextResponse.json({ error: "source invalid" }, { status: 400 });
  }

  const fields = normalizeBs(body);
  const row = {
    business_line,
    entity,
    as_of_date,
    ...fields,
    note: body.note ? String(body.note).slice(0, 2000) : null,
    source,
    updated_at: new Date().toISOString(),
  };

  const { data, error } = await supabase
    .from("kurashift_mq_bs_snapshots")
    .upsert(row, {
      onConflict: "business_line,entity,as_of_date",
    })
    .select("*")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, row: data });
}
