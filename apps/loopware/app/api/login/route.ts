import { NextResponse } from "next/server";
import { SESSION_COOKIE, SESSION_DAYS, safeEqual, sessionValue } from "@/lib/access";

export const runtime = "nodejs";

/** 端末ごとに1回、鍵を入れて Cookie をもらう */
export async function POST(req: Request) {
  const key = process.env.LOOPWARE_ACCESS_KEY || "";
  if (!key) return NextResponse.json({ ok: false, error: "loopware_access_key_unset" }, { status: 503 });
  let given = "";
  try {
    const j = (await req.json()) as { key?: string };
    given = String(j.key || "").trim();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  if (!given || !safeEqual(given, key)) {
    // 総当たりを遅らせる
    await new Promise((r) => setTimeout(r, 800));
    return NextResponse.json({ ok: false, error: "wrong key" }, { status: 401 });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, await sessionValue(key), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_DAYS * 86400,
  });
  return res;
}
