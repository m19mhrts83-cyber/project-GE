import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as
    | { email?: string; password_hash?: string; secret_key?: string }
    | null;
  const email = String(body?.email ?? "").trim().toLowerCase();
  const passwordHash = String(body?.password_hash ?? "");
  const secret = String(body?.secret_key ?? "").trim();

  if (!secret) {
    return NextResponse.json(
      { errorCode: "secret_required", errorMessage: "シークレットキーは必須です" },
      { status: 400 }
    );
  }
  if (secret !== "1162") {
    return NextResponse.json(
      { errorCode: "invalid_secret", errorMessage: "シークレットキーが一致しません" },
      { status: 403 }
    );
  }
  if (!email || !passwordHash) {
    return NextResponse.json({ errorMessage: "メールアドレスとパスワードは必須です" }, { status: 400 });
  }

  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("users")
    .insert([{ email, password_hash: passwordHash, role: "admin", status: "approved" }])
    .select("id")
    .single();

  if (error) {
    return NextResponse.json({ errorMessage: error.message || "登録に失敗しました" }, { status: 400 });
  }
  return NextResponse.json({ id: data.id });
}

