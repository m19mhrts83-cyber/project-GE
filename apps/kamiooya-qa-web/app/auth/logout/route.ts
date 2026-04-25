import { NextResponse } from "next/server";
import { SESSION_COOKIE_NAME } from "@/lib/session";

export const runtime = "nodejs";

export async function POST() {
  const res = NextResponse.json({ success: true });
  res.cookies.set(SESSION_COOKIE_NAME, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: true,
    path: "/",
    maxAge: 0
  });
  return res;
}

