import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { buildSessionToken, SESSION_COOKIE_NAME } from "@/lib/session";
import { toSessionIdString } from "@/lib/ids";

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
  const { data: user, error } = await sb
    .from("users")
    .select("id,email,role,status,password_hash")
    .eq("email", email)
    .eq("password_hash", passwordHash)
    .maybeSingle();

  if (error || !user) {
    return NextResponse.json(
      { errorCode: "invalid_credentials", errorMessage: "メールアドレスまたはパスワードが間違っています" },
      { status: 401 }
    );
  }
  if (user.status !== "approved") {
    return NextResponse.json(
      { errorCode: "not_approved", errorMessage: "管理者の承認待ちです" },
      { status: 403 }
    );
  }

  const res = NextResponse.json({
    user: { id: toSessionIdString(user.id), email: user.email, role: user.role, status: user.status }
  });
  res.cookies.set(SESSION_COOKIE_NAME, buildSessionToken({
    id: toSessionIdString(user.id),
    email: user.email,
    role: user.role,
    status: user.status
  }), {
    httpOnly: true,
    sameSite: "lax",
    secure: true,
    path: "/",
    maxAge: 60 * 60 * 24 * 14
  });
  return res;
}

