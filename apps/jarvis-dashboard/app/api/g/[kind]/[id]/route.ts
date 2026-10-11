import { NextResponse, type NextRequest } from "next/server";
import {
  applyGate,
  htmlPage,
  parseAction,
  sigOk,
  type GateAction,
} from "@/lib/propertyGateAction";

export const runtime = "nodejs";

/**
 * 短縮ゲート URL
 *   Yes: /api/g/y/{deal_id}?s={hmac10}
 *   No:  /api/g/n/{deal_id}?s={hmac10}
 *   詳細: /api/g/d/{deal_id} → trade-desk deals
 */

const DEALS_UI = "https://jarvis-trade-desk.vercel.app/realestate/deals";

function kindToAction(kind: string): GateAction | null {
  const k = kind.trim().toLowerCase();
  if (k === "y" || k === "yes") return "yes";
  if (k === "n" || k === "no") return "no";
  return null;
}

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ kind: string; id: string }> },
) {
  const { kind, id } = await ctx.params;
  const dealId = (id || "").trim();
  const k = (kind || "").trim().toLowerCase();

  if (!dealId || !/^[0-9a-f-]{36}$/i.test(dealId)) {
    return htmlPage("エラー", "deal_id が不正です", false);
  }

  if (k === "d") {
    return NextResponse.redirect(`${DEALS_UI}?deal=${dealId}`, 302);
  }

  const action = kindToAction(k) || parseAction(k);
  if (!action) {
    return htmlPage("エラー", "kind は y / n / d です", false);
  }

  const sig = request.nextUrl.searchParams.get("s");
  if (!sigOk(dealId, action, sig)) {
    return htmlPage("認証エラー", "署名が無効です（リンクが古い可能性があります）", false);
  }

  const result = await applyGate(dealId, action, "slack_short_link");
  return htmlPage(
    result.ok ? (action === "yes" ? "Yes 受付" : "No 受付") : "失敗",
    result.message + (result.job_id ? `\njob_id=${result.job_id}` : ""),
    result.ok,
  );
}

export async function HEAD() {
  return new NextResponse(null, { status: 200 });
}
