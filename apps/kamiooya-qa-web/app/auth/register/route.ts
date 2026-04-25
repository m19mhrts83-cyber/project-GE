import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as
    | { email?: string; password_hash?: string }
    | null;
  const email = String(body?.email ?? "").trim().toLowerCase();
  const passwordHash = String(body?.password_hash ?? "");
  if (!email || !passwordHash) {
    return NextResponse.json({ errorMessage: "メールアドレスとパスワードは必須です" }, { status: 400 });
  }

  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("users")
    .insert([{ email, password_hash: passwordHash, role: "user", status: "pending" }])
    .select("id")
    .single();

  if (error) {
    const msg = error.message || "登録に失敗しました";
    return NextResponse.json({ errorMessage: msg }, { status: 400 });
  }
  return NextResponse.json({ id: data.id });
}

