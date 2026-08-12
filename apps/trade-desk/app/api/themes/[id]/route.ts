import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

const ALLOWED: Record<string, string[]> = {
  draft: ["consulting", "approved", "closed"],
  consulting: ["draft", "approved", "closed"],
  approved: ["executing", "consulting", "closed"],
  executing: ["reviewed", "closed"],
  reviewed: ["closed"],
  closed: ["draft"],
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
    .from("kurashift_themes")
    .select("id, status, title, payload, review_note")
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

  const patch: Record<string, unknown> = {
    status: next,
    updated_at: new Date().toISOString(),
  };
  if (body.review_note != null) {
    patch.review_note = String(body.review_note);
  }

  if (next === "approved") {
    const prev =
      row.payload && typeof row.payload === "object" ? row.payload : {};
    patch.payload = {
      ...prev,
      approved_at: new Date().toISOString(),
      approved_by: user.email ?? user.id,
      live: false,
    };
  }

  const { data, error } = await supabase
    .from("kurashift_themes")
    .update(patch)
    .eq("id", id)
    .select("id, title, status, review_note")
    .single();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, theme: data });
}
