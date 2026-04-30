import { NextResponse } from "next/server";
import { requireUser } from "@/lib/authz";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { withErrorHandler } from "@/lib/routeHandler";

export const runtime = "nodejs";

export const GET = withErrorHandler(async (req) => {
  requireUser(req);
  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("suggested_questions")
    .select("*")
    .order("frequency", { ascending: false })
    .limit(5);
  if (error) {
    return NextResponse.json({ errorMessage: error.message || "取得に失敗しました" }, { status: 500 });
  }
  return NextResponse.json({ questions: data ?? [] });
});

export const POST = withErrorHandler(async (req) => {
  requireUser(req);
  const body = (await req.json().catch(() => null)) as { question_text?: string } | null;
  const text = String(body?.question_text ?? "").trim();
  if (!text) return NextResponse.json({ errorMessage: "質問が空です" }, { status: 400 });
  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("suggested_questions")
    .insert([{ question_text: text, frequency: 1 }])
    .select("id")
    .single();
  if (error) {
    return NextResponse.json({ errorMessage: error.message || "登録に失敗しました" }, { status: 400 });
  }
  return NextResponse.json({ id: data.id });
});
