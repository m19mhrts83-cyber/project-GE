import { NextResponse } from "next/server";
import { requireAdmin } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function POST(req: Request) {
  requireAdmin(req);
  const body = (await req.json().catch(() => null)) as any;
  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("comments")
    .insert([
      {
        source_type: body?.source_type ?? null,
        comment_id: body?.comment_id ?? null,
        posted_at: body?.posted_at ?? null,
        author_name: body?.author_name ?? null,
        author_email: body?.author_email ?? null,
        content: body?.content ?? "",
        parent_comment_id: body?.parent_comment_id ?? null,
        ip_address: body?.ip_address ?? null,
        user_agent: body?.user_agent ?? null
      }
    ])
    .select("id")
    .single();

  if (error) {
    return NextResponse.json({ errorMessage: error.message || "登録に失敗しました" }, { status: 400 });
  }
  return NextResponse.json({ id: data.id });
}

