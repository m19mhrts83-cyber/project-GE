/**
 * loopware の入場確認（Edge／Node どちらでも動く Web Crypto 版）。
 *
 * - 環境変数 LOOPWARE_ACCESS_KEY を決める（Vercel のみ。コードやログに書かない）
 * - 端末ごとに1回 /login で鍵を入れる → 署名つき Cookie（400日。開くたびに延長するので、使っていれば切れない）
 * - Slack からのリンクは ?t=<期限>.<署名>（7日）を付ければ、そのまま入れる
 *   （作り方は linkToken。Jarvis ダッシュボード側も同じ鍵で作る）
 *
 * 判断ログには個人情報（件名・相手・本文）が入るため、鍵が無い本番では
 * 新しい画面（/desk・/misses・/api/log）を開かない。
 */

export const SESSION_COOKIE = "lw_s";
export const SESSION_DAYS = 400; // ブラウザが受け付ける上限。開くたびに延長（middleware）
const LINK_DAYS = 7;

const enc = new TextEncoder();

function b64url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function hmac(key: string, msg: string): Promise<string> {
  const k = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", k, enc.encode(msg)));
}

/** 長さに依らず比べる（時間差で中身が漏れないように） */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

/** Cookie の値。鍵を変えれば全端末が締め出される */
export async function sessionValue(key: string): Promise<string> {
  return hmac(key, "loopware-session-v1");
}

export async function isValidSession(key: string, cookie: string | undefined | null): Promise<boolean> {
  if (!key || !cookie) return false;
  return safeEqual(cookie, await sessionValue(key));
}

/** Slack などから飛ぶリンクに付ける t= の値 */
export async function linkToken(key: string, now: Date = new Date(), days = LINK_DAYS): Promise<string> {
  const exp = Math.floor(now.getTime() / 1000) + days * 86400;
  return `${exp}.${await hmac(key, `loopware-link-v1:${exp}`)}`;
}

export async function isValidLinkToken(key: string, token: string | null | undefined, now: Date = new Date()): Promise<boolean> {
  if (!key || !token) return false;
  const m = /^(\d{9,11})\.([A-Za-z0-9_-]{20,})$/.exec(token);
  if (!m) return false;
  const exp = Number(m[1]);
  if (exp * 1000 < now.getTime()) return false;
  return safeEqual(m[2], await hmac(key, `loopware-link-v1:${exp}`));
}

/** 鍵が無くても開いてよい既存画面（312/313 は個人情報が少なく、従来どおり） */
export function isLegacyOpenPath(path: string, search: URLSearchParams | null = null): boolean {
  // /api/misses?surface=triage はメールの中身を返すので鍵が要る
  if (path === "/api/misses" && search?.get("surface")) return false;
  return (
    path === "/" ||
    path.startsWith("/312") ||
    path.startsWith("/313") ||
    path === "/api/decide" ||
    path === "/api/misses"
  );
}

export function isPublicPath(path: string): boolean {
  return (
    path === "/login" ||
    path === "/api/login" ||
    path.startsWith("/_next/") ||
    path === "/favicon.ico" ||
    path === "/robots.txt"
  );
}
