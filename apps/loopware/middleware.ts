import { NextResponse, type NextRequest } from "next/server";
import {
  SESSION_COOKIE,
  SESSION_DAYS,
  isLegacyOpenPath,
  isPublicPath,
  isValidLinkToken,
  isValidSession,
  sessionValue,
} from "@/lib/access";

/** 入場確認。仕組みは lib/access.ts の説明を参照 */
export async function middleware(req: NextRequest) {
  const path = req.nextUrl.pathname;
  if (isPublicPath(path)) return NextResponse.next();

  const key = process.env.LOOPWARE_ACCESS_KEY || "";
  const isApi = path.startsWith("/api/");

  if (!key) {
    if (process.env.NODE_ENV !== "production" || isLegacyOpenPath(path, req.nextUrl.searchParams)) return NextResponse.next();
    if (isApi) {
      return NextResponse.json({ ok: false, error: "loopware_access_key_unset" }, { status: 503 });
    }
    const u = req.nextUrl.clone();
    u.pathname = "/login";
    u.search = "?setup=1";
    return NextResponse.redirect(u);
  }

  const cookie = req.cookies.get(SESSION_COOKIE)?.value;
  if (await isValidSession(key, cookie)) {
    // 開くたびに期限を延ばす（使っている端末では鍵を入れ直さずに済む）
    const res = NextResponse.next();
    res.cookies.set(SESSION_COOKIE, cookie as string, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: SESSION_DAYS * 86400,
    });
    return res;
  }

  // Slack からのリンク（?t=）なら、その端末を覚えて t を外したURLへ
  const t = req.nextUrl.searchParams.get("t");
  if (!isApi && (await isValidLinkToken(key, t))) {
    const u = req.nextUrl.clone();
    u.searchParams.delete("t");
    const res = NextResponse.redirect(u);
    res.cookies.set(SESSION_COOKIE, await sessionValue(key), {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: SESSION_DAYS * 86400,
    });
    return res;
  }

  if (isApi) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const u = req.nextUrl.clone();
  u.pathname = "/login";
  u.search = `?next=${encodeURIComponent(path + req.nextUrl.search)}`;
  return NextResponse.redirect(u);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
