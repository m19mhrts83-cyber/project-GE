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
  const { data: updated, error: updateErr } = await sb
    .from("users")
    .update({ password_hash: passwordHash, role: "admin", status: "approved" })
    .eq("email", email)
    .select("id,email")
    .maybeSingle();

  if (updateErr || !updated) {
    return NextResponse.json(
      {
        errorCode: "user_not_found",
        errorMessage: "このメールアドレスは未登録のため、新規の管理者登録処理に切り替えてください"
      },
      { status: 404 }
    );
  }

  return NextResponse.json({ success: true });
}

