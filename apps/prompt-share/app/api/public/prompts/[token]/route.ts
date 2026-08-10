import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ token: string }> };

export async function GET(_req: Request, ctx: Ctx) {
  const { token } = await ctx.params;
  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("prompts")
    .select(
      "id,title,description,template,variables,public_token,status,access_level,group_id,view_count,generate_count,copy_count"
    )
    .eq("public_token", token)
    .maybeSingle();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!data || data.status !== "published" || data.access_level !== "public") {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  let group = null;
  if (data.group_id) {
    const { data: g } = await sb
      .from("prompt_groups")
      .select("id,name,slug")
      .eq("id", data.group_id)
      .maybeSingle();
    group = g;
  }

  return NextResponse.json({ prompt: data, group });
}
