import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

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
  if (!title) {
    return NextResponse.json({ error: "title required" }, { status: 400 });
  }

  const amountRaw = body.amount_jpy;
  const amount =
    amountRaw === "" || amountRaw == null ? null : Number(amountRaw);

  const { data, error } = await supabase
    .from("kurashift_themes")
    .insert({
      title,
      hypothesis: String(body.hypothesis || ""),
      amount_jpy: Number.isFinite(amount as number) ? amount : null,
      duration_note: body.duration_note ? String(body.duration_note) : null,
      funding_path: body.funding_path ? String(body.funding_path) : null,
      status: "draft",
      payload: {
        source: "app_form",
        created_by: user.email ?? user.id,
      },
    })
    .select("id, title, status")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, theme: data });
}
