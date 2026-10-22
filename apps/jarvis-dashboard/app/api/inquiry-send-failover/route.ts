import { NextResponse, type NextRequest } from "next/server";
import { runInquirySendFailover } from "@/lib/inquirySendFailover";

export const runtime = "nodejs";
export const maxDuration = 60;

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) {
    out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return out === 0;
}

function authorized(request: NextRequest): boolean {
  const candidates = [
    process.env.CRON_SECRET,
    process.env.PROPERTY_GATE_ACTION_TOKEN,
    process.env.INQUIRY_FAILOVER_SECRET,
  ]
    .map((x) => (x || "").trim())
    .filter(Boolean);
  if (!candidates.length) return false;
  const got = (
    request.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ||
    request.headers.get("x-inquiry-failover-secret") ||
    ""
  ).trim();
  if (!got) return false;
  return candidates.some((c) => timingSafeEqual(got, c));
}

/**
 * GET/POST /api/inquiry-send-failover
 * Mac worker が 5 分以上 queued のままの first_inquiry を Vercel 定型送信。
 * Auth: Bearer CRON_SECRET | PROPERTY_GATE_ACTION_TOKEN | INQUIRY_FAILOVER_SECRET
 * 停止: INQUIRY_VERCEL_FAILOVER=0
 */
async function handle(request: NextRequest) {
  if (!authorized(request)) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  const result = await runInquirySendFailover();
  return NextResponse.json(result, { status: result.ok ? 200 : 500 });
}

export async function GET(request: NextRequest) {
  return handle(request);
}

export async function POST(request: NextRequest) {
  return handle(request);
}
