import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const groupSlug = searchParams.get("group");
  const sb = supabaseAdmin();

  let groupId: number | null = null;
  if (groupSlug) {
    const { data: g } = await sb
      .from("prompt_groups")
      .select("id,access_level")
      .eq("slug", groupSlug)
      .maybeSingle();
    if (!g || g.access_level !== "public") {
      return NextResponse.json({ prompts: [], group: null });
    }
    groupId = Number(g.id);
  }

  let q = sb
    .from("prompts")
    .select("id,title,description,public_token,group_id,copy_count,view_count,generate_count,updated_at")
    .eq("status", "published")
    .eq("access_level", "public")
    .order("updated_at", { ascending: false });
  if (groupId != null) q = q.eq("group_id", groupId);

  const { data, error } = await q;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ prompts: data || [] });
}
