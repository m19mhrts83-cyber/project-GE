import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { randomPublicToken, syncVariablesFromTemplate, type PromptVariable } from "@/lib/prompts";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

function errRes(e: unknown) {
  const status = (e as { status?: number })?.status || 500;
  const message = e instanceof Error ? e.message : "error";
  return NextResponse.json({ error: message }, { status });
}

export async function GET(req: Request, ctx: Ctx) {
  try {
    requireAdmin(req);
    const { id } = await ctx.params;
    const sb = supabaseAdmin();
    const { data, error } = await sb.from("prompts").select("*").eq("id", Number(id)).maybeSingle();
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    if (!data) return NextResponse.json({ error: "not found" }, { status: 404 });
    return NextResponse.json({ prompt: data });
  } catch (e) {
    return errRes(e);
  }
}

export async function PUT(req: Request, ctx: Ctx) {
  try {
    requireAdmin(req);
    const { id } = await ctx.params;
    const body = (await req.json().catch(() => null)) as {
      title?: string;
      description?: string;
      template?: string;
      variables?: PromptVariable[];
      group_id?: number | null;
      status?: "draft" | "published";
      access_level?: "public" | "member";
      regenerate_token?: boolean;
    } | null;

    const sb = supabaseAdmin();
    const { data: existing } = await sb.from("prompts").select("*").eq("id", Number(id)).maybeSingle();
    if (!existing) return NextResponse.json({ error: "not found" }, { status: 404 });

    const template = body?.template != null ? String(body.template) : String(existing.template);
    const variables =
      body?.variables != null
        ? body.variables
        : syncVariablesFromTemplate(template, (existing.variables as PromptVariable[]) || []);

    const patch: Record<string, unknown> = {
      updated_at: new Date().toISOString()
    };
    if (body?.title != null) patch.title = String(body.title).trim();
    if (body?.description != null) patch.description = String(body.description);
    if (body?.template != null) patch.template = template;
    patch.variables = variables;
    if (body?.group_id !== undefined) patch.group_id = body.group_id;
    if (body?.status) patch.status = body.status;
    if (body?.access_level) patch.access_level = body.access_level;
    if (body?.regenerate_token) patch.public_token = randomPublicToken();

    const { data, error } = await sb
      .from("prompts")
      .update(patch)
      .eq("id", Number(id))
      .select("*")
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ prompt: data });
  } catch (e) {
    return errRes(e);
  }
}

export async function DELETE(req: Request, ctx: Ctx) {
  try {
    requireAdmin(req);
    const { id } = await ctx.params;
    const sb = supabaseAdmin();
    const { error } = await sb.from("prompts").delete().eq("id", Number(id));
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ ok: true });
  } catch (e) {
    return errRes(e);
  }
}
