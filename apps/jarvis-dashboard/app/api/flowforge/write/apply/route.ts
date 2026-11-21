import { proxyAuthorized } from "@/lib/flowforgeShareProxy";
import { handleWriteRoute } from "@/lib/flowforgeWriteUpstream";

export const runtime = "nodejs";
export const maxDuration = 60;

/**
 * POST /api/flowforge/write/apply（試作・非公式 API。docs 54b「書き込み（試作）」）
 * Auth: Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY または x-flowforge-read-key（?key= 不可）
 * 止め方: FLOWFORGE_WRITE_ALLOWED_FLOW_IDS を空に / FLOWFORGE_WRITE_DISABLE=1
 */
export async function POST(request: Request) {
  return handleWriteRoute("apply", request, (h) => proxyAuthorized(h));
}
