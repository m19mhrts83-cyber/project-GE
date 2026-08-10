import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { slugify } from "@/lib/prompts";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

function errRes(e: unknown) {
  const status = (e as { status?: number })?.status || 500;
  const message = e instanceof Error ? e.message : "error";
  return NextResponse.json({ error: message }, { status });
}

export async function PUT(req: Request, ctx: Ctx) {
  try {
    requireAdmin(req);
    const { id } = await ctx.params;
    const body = (await req.json().catch(() => null)) as {
      name?: string;
      slug?: string;
      description?: string;
      sort_order?: number;
      access_level?: "public" | "member";
    } | null;
    const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };
    if (body?.name != null) patch.name = String(body.name).trim();
    if (body?.slug != null) patch.slug = String(body.slug).trim() || slugify(String(body.name || "group"));
    if (body?.description != null) patch.description = String(body.description);
    if (body?.sort_order != null) patch.sort_order = Number(body.sort_order);
    if (body?.access_level) patch.access_level = body.access_level;

    const sb = supabaseAdmin();
    const { data, error } = await sb
      .from("prompt_groups")
      .update(patch)
      .eq("id", Number(id))
      .select("*")
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ group: data });
  } catch (e) {
    return errRes(e);
  }
}

export async function DELETE(req: Request, ctx: Ctx) {
  try {
    requireAdmin(req);
    const { id } = await ctx.params;
    const sb = supabaseAdmin();
    const { error } = await sb.from("prompt_groups").delete().eq("id", Number(id));
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ ok: true });
  } catch (e) {
    return errRes(e);
  }
}
