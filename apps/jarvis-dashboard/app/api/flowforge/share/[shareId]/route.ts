import { NextResponse, type NextRequest } from "next/server";
import {
  extractShareId,
  fetchFlowforgeShare,
  proxyAuthorized,
  summarizeFlowPayload,
} from "@/lib/flowforgeShareProxy";

export const runtime = "nodejs";
export const maxDuration = 30;

/**
 * GET /api/flowforge/share/{shareId}?summary=1
 * Auth: Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY
 *       または x-flowforge-read-key
 * 停止: FLOWFORGE_READ_PROXY_DISABLE=1
 */
export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ shareId: string }> },
) {
  if ((process.env.FLOWFORGE_READ_PROXY_DISABLE || "").trim() === "1") {
    return NextResponse.json({ ok: false, error: "disabled" }, { status: 503 });
  }
  const secretSet = Boolean((process.env.FLOWFORGE_READ_PROXY_KEY || "").trim());
  if (!proxyAuthorized(request.headers)) {
    return NextResponse.json(
      {
        ok: false,
        error: secretSet ? "unauthorized" : "FLOWFORGE_READ_PROXY_KEY 未設定",
      },
      { status: secretSet ? 401 : 503 },
    );
  }

  const { shareId: raw } = await ctx.params;
  const shareId = extractShareId(raw);
  if (!shareId) {
    return NextResponse.json({ ok: false, error: "invalid_share_id" }, { status: 400 });
  }

  const upstream = await fetchFlowforgeShare(shareId);
  if (!upstream.ok) {
    return NextResponse.json(
      { ok: false, error: upstream.error, upstream: upstream.upstream ?? null, shareId },
      { status: upstream.status },
    );
  }

  const summaryOnly = new URL(request.url).searchParams.get("summary") === "1";
  if (summaryOnly) {
    return NextResponse.json({
      ok: true,
      shareId,
      summary: summarizeFlowPayload(upstream.body),
    });
  }
  return NextResponse.json({ ok: true, shareId, ...(upstream.body as object) });
}
