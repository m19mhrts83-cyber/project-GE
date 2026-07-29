import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { hashPasswordForStorage } from "@/lib/passwords";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as
    | { email?: string; password_hash?: string; member_no?: string }
    | null;
  const email = String(body?.email ?? "").trim().toLowerCase();
  const password = String(body?.password_hash ?? "");
  const memberNo = String(body?.member_no ?? "").trim();
  if (!email || !password) {
    return NextResponse.json({ errorMessage: "メールアドレスとパスワードは必須です" }, { status: 400 });
  }
  if (!memberNo) {
    return NextResponse.json({ errorMessage: "会員番号は必須です" }, { status: 400 });
  }

  const passwordHash = await hashPasswordForStorage(password);
  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("users")
    .insert([
      {
        email,
        password_hash: passwordHash,
        member_no: memberNo,
        role: "user",
        status: "pending",
      },
    ])
    .select("id")
    .single();

  if (error) {
    const msg = error.message || "登録に失敗しました";
    return NextResponse.json({ errorMessage: msg }, { status: 400 });
  }
  return NextResponse.json({ id: data.id });
}
