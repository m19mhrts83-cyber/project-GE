import { createHmac } from "node:crypto";
import { LOOPWARE_URL } from "@/lib/nav";

/**
 * ループウェアへ「鍵を入れずに」入れるリンク（?t=<期限>.<署名>・7日）。
 * 形は apps/loopware/lib/access.ts の linkToken と同じ。鍵（LOOPWARE_ACCESS_KEY）が無ければ素のリンク。
 * サーバー側だけで使う（鍵をブラウザに出さない）。
 */
export function loopwareLinkToken(key: string, now: Date = new Date(), days = 7): string {
  const exp = Math.floor(now.getTime() / 1000) + days * 86400;
  const sig = createHmac("sha256", key).update(`loopware-link-v1:${exp}`).digest("base64url");
  return `${exp}.${sig}`;
}

export function loopwareHref(path: string, params: Record<string, string> = {}): string {
  const u = new URL(path, LOOPWARE_URL.replace(/\/$/, "") + "/");
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
  const key = (process.env.LOOPWARE_ACCESS_KEY || "").trim();
  if (key) u.searchParams.set("t", loopwareLinkToken(key));
  return u.toString();
}
