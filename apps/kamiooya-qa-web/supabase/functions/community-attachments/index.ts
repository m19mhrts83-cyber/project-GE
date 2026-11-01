// Raimo authenticates the password locally. Only its backend can issue sessions.
// Each metadata/read request rechecks the current Raimo membership status.
declare const Deno: { env: { get(key: string): string | undefined }; serve(handler: (req: Request) => Promise<Response>): void };

type Config = { projectUrl: string; serviceKey: string; proxySecret: string; sessionSecret: string; raimoOrigin: string; statusUrl: string };
const BUCKET = "community-attachments";
const AUDIENCE = "kamiooya-attachments";
const encoder = new TextEncoder();
const b64 = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
const unb64 = (s: string) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
async function hmac(secret: string, value: string): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(value)));
}
async function sameSecret(a: string, b: string): Promise<boolean> {
  const hash = async (s: string) => new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(s)));
  const [x, y] = await Promise.all([hash(a), hash(b)]);
  return x.reduce((n, v, i) => n | (v ^ y[i]), 0) === 0;
}
export async function issueSession(uid: string, secret: string, now: number): Promise<string> {
  if (!/^[a-zA-Z0-9_-]{1,100}$/.test(uid)) throw new Error("invalid_user");
  const payload = b64(encoder.encode(JSON.stringify({ v: 1, aud: AUDIENCE, uid, exp: Math.floor(now / 1000) + 28800 })));
  return payload + "." + b64(await hmac(secret, payload));
}
export async function sessionUser(token: string, secret: string, now: number): Promise<string | null> {
  try {
    if (token.length > 2000) return null;
    const parts = token.split(".");
    if (parts.length !== 2 || !await sameSecret(parts[1], b64(await hmac(secret, parts[0])))) return null;
    const p = JSON.parse(new TextDecoder().decode(unb64(parts[0])));
    if (p.v !== 1 || p.aud !== AUDIENCE || !Number.isInteger(p.exp) || p.exp <= now / 1000 || !/^[a-zA-Z0-9_-]{1,100}$/.test(p.uid)) return null;
    return p.uid;
  } catch { return null; }
}

export function createHandler(cfg: Config, transport: typeof fetch = fetch, now: () => number = Date.now) {
  return async (req: Request): Promise<Response> => {
    const origin = req.headers.get("origin");
    const headers = { "Content-Type": "application/json", "Cache-Control": "no-store", "Vary": "Origin",
      ...(origin === cfg.raimoOrigin ? { "Access-Control-Allow-Origin": cfg.raimoOrigin,
        "Access-Control-Allow-Headers": "authorization, content-type, apikey", "Access-Control-Allow-Methods": "POST, OPTIONS" } : {}) };
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers });
    if (origin && origin !== cfg.raimoOrigin) return json({ error: "forbidden_origin" }, 403);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers });
    if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    if (!cfg.serviceKey || cfg.proxySecret.length < 32 || cfg.sessionSecret.length < 32 || !cfg.statusUrl.startsWith(cfg.raimoOrigin + "/")) return json({ error: "service_not_configured" }, 503);
    try {
      const text = await req.text();
      if (text.length > 16384) return json({ error: "request_too_large" }, 413);
      let body;
      try { body = JSON.parse(text); } catch { return json({ error: "invalid_request" }, 400); }
      const op = body?.operation;
      const authorization = req.headers.get("authorization") || "";
      if (op === "session") {
        if (!await sameSecret(authorization, "Bearer " + cfg.proxySecret)) return json({ error: "unauthorized" }, 401);
        const uid = String(body.user_id ?? "");
        return json({ token: await issueSession(uid, cfg.sessionSecret, now()), expires_in: 28800 });
      }
      if (!["index", "list", "open"].includes(op)) return json({ error: "invalid_operation" }, 400);
      const uid = await sessionUser(authorization.replace(/^Bearer /, ""), cfg.sessionSecret, now());
      if (!uid) return json({ error: "login_required" }, 401);
      // Do not trust browser user_id/role/status or a stale login result.
      const statusResponse = await transport(cfg.statusUrl, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: uid, secret: cfg.proxySecret }), signal: AbortSignal.timeout(15000) });
      if (!statusResponse.ok) return json({ error: "membership_check_unavailable" }, 503);
      const member = await statusResponse.json();
      if (String(member.user_id) !== uid || member.status !== "approved" || !["user", "admin", "master_admin"].includes(member.role)) return json({ error: "membership_required" }, 403);
      const auth = { apikey: cfg.serviceKey, Authorization: "Bearer " + cfg.serviceKey };
      const query = new URLSearchParams();
      if (op === "open") {
        if (!/^[0-9a-f]{64}$/.test(body.attachment_id || "")) return json({ error: "invalid_attachment" }, 400);
        query.set("select", "id,bucket,storage_path"); query.set("id", "eq." + body.attachment_id); query.set("limit", "1");
      } else {
        query.set("select", "id,comment_id,original_name,content_type,byte_size"); query.set("order", "id.asc");
        if (op === "list") {
          if (!/^[0-9]+$/.test(body.comment_id || "")) return json({ error: "invalid_comment" }, 400);
          query.set("comment_id", "eq." + body.comment_id); query.set("limit", "100");
        } else {
          const offset = body.offset ?? 0;
          if (!Number.isInteger(offset) || offset < 0 || offset > 100000) return json({ error: "invalid_offset" }, 400);
          query.set("limit", "500"); query.set("offset", String(offset));
        }
      }
      const metaResponse = await transport(cfg.projectUrl + "/rest/v1/community_attachments?" + query, { headers: auth, signal: AbortSignal.timeout(15000) });
      if (!metaResponse.ok) return json({ error: "attachments_unavailable" }, 503);
      const rows = await metaResponse.json();
      if (op !== "open") return json({ attachments: rows, next_offset: op === "index" && rows.length === 500 ? (body.offset ?? 0) + 500 : null });
      const row = rows[0];
      if (!row) return json({ error: "not_found" }, 404);
      if (row.bucket !== BUCKET || !/^comments\/[0-9]+\/[0-9a-f]{64}\.(jpg|png|pdf|xlsx|docx|pptx|zip|webp|heic|doc|csv)$/.test(row.storage_path)) return json({ error: "invalid_storage_record" }, 500);
      const signResponse = await transport(cfg.projectUrl + "/storage/v1/object/sign/" + BUCKET + "/" + row.storage_path, {
        method: "POST", headers: { ...auth, "Content-Type": "application/json" }, body: JSON.stringify({ expiresIn: 60 }), signal: AbortSignal.timeout(15000) });
      if (!signResponse.ok) return json({ error: "file_unavailable" }, 503);
      const signed = await signResponse.json();
      const path = String(signed.signedURL || "");
      if (!path.startsWith("/object/sign/" + BUCKET + "/")) return json({ error: "invalid_storage_response" }, 502);
      return json({ url: cfg.projectUrl + "/storage/v1" + path, expires_in: 60 });
    } catch {
      // Do not log passwords, session tokens, signed URLs, or upstream response bodies.
      return json({ error: "attachments_unavailable" }, 503);
    }
  };
}

if (typeof Deno !== "undefined") Deno.serve(createHandler({
  projectUrl: Deno.env.get("SUPABASE_URL") || "", serviceKey: Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "",
  proxySecret: Deno.env.get("COMMUNITY_ATTACHMENTS_PROXY_SECRET") || "", sessionSecret: Deno.env.get("COMMUNITY_ATTACHMENTS_SESSION_SECRET") || "",
  raimoOrigin: "https://ma-54t2keqdelz3.raimo-app.buzz",
  statusUrl: "https://ma-54t2keqdelz3.raimo-app.buzz/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0/internal/attachment-user-status",
}));
