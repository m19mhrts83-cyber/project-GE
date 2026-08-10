import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function GET() {
  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("prompt_groups")
    .select("id,name,slug,description,sort_order")
    .eq("access_level", "public")
    .order("sort_order", { ascending: true })
    .order("id", { ascending: true });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ groups: data || [] });
}
