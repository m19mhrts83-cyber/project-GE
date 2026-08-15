import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const { data, error } = await supabase
    .from("kurashift_mq_account_map")
    .select("*")
    .order("priority", { ascending: true });
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, rows: data ?? [] });
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
  if (typeof body.approved === "boolean") patch.approved = body.approved;
  if (body.mq_element) patch.mq_element = String(body.mq_element);
  if (body.note != null) patch.note = String(body.note).slice(0, 500);
  if (body.combine_treatment) {
    patch.combine_treatment = String(body.combine_treatment);
  }

  const { data, error } = await supabase
    .from("kurashift_mq_account_map")
    .update(patch)
    .eq("id", id)
    .select("*")
    .single();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, row: data });
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
  const row = {
    business_line: String(body.business_line || "realestate"),
    category_match: String(body.category_match || ""),
    subcategory_match: String(body.subcategory_match || ""),
    entity_match: String(body.entity_match || ""),
    mq_element: String(body.mq_element || "f"),
    combine_treatment: String(body.combine_treatment || "include"),
    priority: Number(body.priority) || 100,
    approved: Boolean(body.approved),
    note: body.note ? String(body.note).slice(0, 500) : null,
  };
  const { data, error } = await supabase
    .from("kurashift_mq_account_map")
    .insert(row)
    .select("*")
    .single();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, row: data });
}
