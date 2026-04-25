import { decodeSessionToken, getCookieFromHeader, SESSION_COOKIE_NAME } from "@/lib/session";

export function requireUser(req: Request) {
  const token = getCookieFromHeader(req.headers.get("cookie"), SESSION_COOKIE_NAME);
  const u = token ? decodeSessionToken(token) : null;
  if (!u) {
    const err = new Error("unauthorized");
    (err as any).status = 401;
    throw err;
  }
  if (u.status !== "approved") {
    const err = new Error("not_approved");
    (err as any).status = 403;
    throw err;
  }
  return u;
}

export function requireAdmin(req: Request) {
  const u = requireUser(req);
  if (u.role !== "admin") {
    const err = new Error("forbidden");
    (err as any).status = 403;
    throw err;
  }
  return u;
}

