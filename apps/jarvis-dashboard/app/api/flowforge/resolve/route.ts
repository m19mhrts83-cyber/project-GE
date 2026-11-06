import { NextResponse, type NextRequest } from "next/server";
import {
  fetchFlowforgeShare,
  proxyAuthorized,
  resolveShareId,
  summarizeFlowPayload,
} from "@/lib/flowforgeShareProxy";

export const runtime = "nodejs";
export const maxDuration = 30;

/**
 * GET /api/flowforge/resolve?shareId=… | url=… | flowId=… | agentId=…
 * Optional: summary=1
 * Auth: Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY
 *       または x-flowforge-read-key
 */
export async function GET(request: NextRequest) {
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

  const q = request.nextUrl.searchParams;
  const resolved = resolveShareId({
    shareId: q.get("shareId"),
    url: q.get("url"),
    flowId: q.get("flowId") || q.get("flow_id"),
    agentId: q.get("agentId") || q.get("agent_id"),
  });
  if ("error" in resolved) {
    return NextResponse.json(
      { ok: false, error: resolved.error },
      { status: resolved.status },
    );
  }

  const upstream = await fetchFlowforgeShare(resolved.shareId);
  if (!upstream.ok) {
    return NextResponse.json(
      {
        ok: false,
        error: upstream.error,
        upstream: upstream.upstream ?? null,
        shareId: resolved.shareId,
      },
      { status: upstream.status },
    );
  }

  const summaryOnly = q.get("summary") === "1";
  if (summaryOnly) {
    return NextResponse.json({
      ok: true,
      shareId: resolved.shareId,
      summary: summarizeFlowPayload(upstream.body),
    });
  }
  return NextResponse.json({
    ok: true,
    shareId: resolved.shareId,
    ...(upstream.body as object),
  });
}
