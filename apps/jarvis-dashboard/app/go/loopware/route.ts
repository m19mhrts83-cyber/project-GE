import { NextResponse, type NextRequest } from "next/server";
import { loopwareHref } from "@/lib/loopwareLink";

/**
 * ループウェアへの入口（2026-11-10）。
 * Claude などが貼るリンクは鍵の通行証を付けられないので、ダッシュボードのログイン（middleware）を通ってから
 * 通行証つきのループウェアへ飛ばす。例: /go/loopware?to=/desk
 */
export const dynamic = "force-dynamic";

export function GET(req: NextRequest) {
  const to = req.nextUrl.searchParams.get("to") || "/desk";
  // ループウェア内のパスだけ（外へは飛ばさない）
  const path = to.startsWith("/") && !to.startsWith("//") ? to : "/desk";
  const [p, q = ""] = path.split("?");
  const params: Record<string, string> = {};
  for (const [k, v] of new URLSearchParams(q)) if (k !== "t") params[k] = v;
  return NextResponse.redirect(loopwareHref(p, params), 302);
}
