import { createHmac, timingSafeEqual } from "node:crypto";

export type SessionUser = {
  id: string;
  email: string;
  role: "user" | "admin";
  status: "pending" | "approved";
};

export const SESSION_COOKIE_NAME = "kamiooya_session";

function requireEnv(key: string): string {
  const v = process.env[key]?.trim();
  if (!v) throw new Error(`Missing env: ${key}`);
  return v;
}

function sign(payload: string): string {
  const secret = requireEnv("SESSION_SECRET");
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

export function decodeSessionToken(token: string): SessionUser | null {
  const [payload, sig] = String(token || "").split(".", 2);
  if (!payload || !sig) return null;
  const expected = sign(payload);
  try {
    const a = Buffer.from(sig);
    const b = Buffer.from(expected);
    if (a.length !== b.length) return null;
    if (!timingSafeEqual(a, b)) return null;
  } catch {
    return null;
  }
  try {
    const json = Buffer.from(payload, "base64url").toString("utf-8");
    const parsed = JSON.parse(json);
    const u = parsed?.user;
    if (!u || !u.id || !u.email || !u.role || !u.status) return null;
    return u as SessionUser;
  } catch {
    return null;
  }
}

export function buildSessionToken(user: SessionUser): string {
  const now = Date.now();
  const payload = Buffer.from(
    JSON.stringify({ v: 1, iat: now, user }),
    "utf-8"
  ).toString("base64url");
  const sig = sign(payload);
  return `${payload}.${sig}`;
}

export function getCookieFromHeader(cookieHeader: string | null, name: string): string | null {
  const raw = String(cookieHeader || "");
  if (!raw) return null;
  const parts = raw.split(/;\s*/g);
  for (const p of parts) {
    const idx = p.indexOf("=");
    if (idx === -1) continue;
    const k = p.slice(0, idx).trim();
    if (k !== name) continue;
    return decodeURIComponent(p.slice(idx + 1));
  }
  return null;
}

