import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { randomPublicToken, syncVariablesFromTemplate, type PromptVariable } from "@/lib/prompts";

export const runtime = "nodejs";

function errRes(e: unknown) {
  const status = (e as { status?: number })?.status || 500;
  const message = e instanceof Error ? e.message : "error";
  return NextResponse.json({ error: message }, { status });
}

export async function GET(req: Request) {
  try {
    requireAdmin(req);
    const sb = supabaseAdmin();
    const { data, error } = await sb
      .from("prompts")
      .select(
        "id,title,description,public_token,status,access_level,group_id,view_count,generate_count,copy_count,updated_at,created_at"
      )
      .order("updated_at", { ascending: false });
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ prompts: data || [] });
  } catch (e) {
    return errRes(e);
  }
}

export async function POST(req: Request) {
  try {
    const admin = requireAdmin(req);
    const body = (await req.json().catch(() => null)) as {
      title?: string;
      description?: string;
      template?: string;
      variables?: PromptVariable[];
      group_id?: number | null;
      status?: "draft" | "published";
      access_level?: "public" | "member";
    } | null;

    const title = String(body?.title ?? "").trim();
    if (!title) return NextResponse.json({ error: "タイトルは必須です" }, { status: 400 });

    const template = String(body?.template ?? "");
    const variables = body?.variables?.length
      ? body.variables
      : syncVariablesFromTemplate(template, []);

    const sb = supabaseAdmin();
    const { data, error } = await sb
      .from("prompts")
      .insert({
        title,
        description: String(body?.description ?? ""),
        template,
        variables,
        group_id: body?.group_id ?? null,
        status: body?.status === "published" ? "published" : "draft",
        access_level: body?.access_level === "member" ? "member" : "public",
        public_token: randomPublicToken(),
        created_by: Number(admin.id)
      })
      .select("*")
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ prompt: data });
  } catch (e) {
    return errRes(e);
  }
}
