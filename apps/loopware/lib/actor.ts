/**
 * 入った人（owner＝松野さん／bot＝ボット用の鍵）をサーバ側で読む。
 * middleware が Cookie の署名から x-lw-actor を付け直す（外から付けた値は捨てる）。
 * ヘッダが無い（鍵なしで開く旧画面・開発）時は owner。
 */
import { ACTOR_HEADER, BOT_FORBIDDEN_BODY, type Actor } from "@/lib/access";

export function actorFromHeaders(h: { get(name: string): string | null } | null | undefined): Actor {
  return h?.get(ACTOR_HEADER) === "bot" ? "bot" : "owner";
}

/** Route Handler から呼ぶ。取れなければ owner */
export async function currentActor(req?: Request): Promise<Actor> {
  if (req) return actorFromHeaders(req.headers);
  try {
    const { headers } = await import("next/headers");
    return actorFromHeaders(await headers());
  } catch {
    return "owner";
  }
}

/** ボットなら 403 の Response を返す。外に届く操作の入口で使う */
export async function botForbidden(req?: Request): Promise<Response | null> {
  if ((await currentActor(req)) !== "bot") return null;
  return Response.json(BOT_FORBIDDEN_BODY, { status: 403 });
}
