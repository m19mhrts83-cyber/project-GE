import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { buildSessionToken, SESSION_COOKIE_NAME } from "@/lib/session";
import { verifyPassword } from "@/lib/passwords";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as
    | { email?: string; password?: string }
    | null;
  const email = String(body?.email ?? "").trim().toLowerCase();
  const password = String(body?.password ?? "");
  if (!email || !password) {
    return NextResponse.json({ error: "メールアドレスとパスワードは必須です" }, { status: 400 });
  }

  const sb = supabaseAdmin();
  const { data: user, error } = await sb
    .from("users")
    .select("id,email,role,status,password_hash")
    .eq("email", email)
    .maybeSingle();

  if (error || !user) {
    return NextResponse.json({ error: "メールアドレスまたはパスワードが間違っています" }, { status: 401 });
  }
  const ok = await verifyPassword(password, String(user.password_hash ?? ""));
  if (!ok) {
    return NextResponse.json({ error: "メールアドレスまたはパスワードが間違っています" }, { status: 401 });
  }
  if (user.status !== "approved") {
    return NextResponse.json({ error: "管理者の承認待ちです" }, { status: 403 });
  }
  if (user.role !== "admin") {
    return NextResponse.json({ error: "管理者権限が必要です" }, { status: 403 });
  }

  const sessionUser = {
    id: String(user.id),
    email: user.email as string,
    role: user.role as "user" | "admin",
    status: user.status as "pending" | "approved"
  };
  const res = NextResponse.json({ user: sessionUser });
  res.cookies.set(SESSION_COOKIE_NAME, buildSessionToken(sessionUser), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 14
  });
  return res;
}
