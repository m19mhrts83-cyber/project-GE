import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { slugify } from "@/lib/prompts";

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
      .from("prompt_groups")
      .select("*")
      .order("sort_order", { ascending: true })
      .order("id", { ascending: true });
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ groups: data || [] });
  } catch (e) {
    return errRes(e);
  }
}

export async function POST(req: Request) {
  try {
    requireAdmin(req);
    const body = (await req.json().catch(() => null)) as {
      name?: string;
      slug?: string;
      description?: string;
      sort_order?: number;
      access_level?: "public" | "member";
    } | null;
    const name = String(body?.name ?? "").trim();
    if (!name) return NextResponse.json({ error: "名前は必須です" }, { status: 400 });
    const slug = String(body?.slug ?? "").trim() || slugify(name);
    const sb = supabaseAdmin();
    const { data, error } = await sb
      .from("prompt_groups")
      .insert({
        name,
        slug,
        description: String(body?.description ?? ""),
        sort_order: Number(body?.sort_order ?? 0),
        access_level: body?.access_level === "member" ? "member" : "public"
      })
      .select("*")
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ group: data });
  } catch (e) {
    return errRes(e);
  }
}
