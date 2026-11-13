import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { bearerMatches } from "@/lib/obsidianReviewAgent";

export const runtime = "nodejs";
export const maxDuration = 15;

function unavailable() {
  return NextResponse.json({ ok: false, error: "Vault read queue is not configured" }, { status: 503 });
}

/** Mac posts bounded search results; ChatGPT fetches them with a separate read key. */
export async function POST(request: NextRequest) {
  if (!bearerMatches(request, "OBSIDIAN_VAULT_POLL_KEY", [
    "OBSIDIAN_REVIEW_SUBMIT_KEY", "OBSIDIAN_REVIEW_POLL_KEY", "OBSIDIAN_REVIEW_READ_KEY", "OBSIDIAN_REVIEW_MONITOR_KEY",
  ])) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  const requestId = typeof body.request_id === "string" ? body.request_id.trim() : "";
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId)) {
    return NextResponse.json({ ok: false, error: "invalid_request_id" }, { status: 400 });
  }
  const result = body.result;
  const errorCode = typeof body.error_code === "string" ? body.error_code.slice(0, 80) : null;
  if ((!errorCode && (!result || typeof result !== "object")) || JSON.stringify(result ?? {}).length > 180_000) {
    return NextResponse.json({ ok: false, error: "invalid_result" }, { status: 400 });
  }
  const supabase = createServiceClient();
  if (!supabase) return unavailable();
  const { data, error } = await supabase
    .from("obsidian_vault_read_requests")
    .update({
      status: errorCode ? "failed" : "completed",
      result: errorCode ? null : result,
      error_code: errorCode,
      completed_at: new Date().toISOString(),
    })
    .eq("id", requestId)
    .eq("status", "processing")
    .gt("expires_at", new Date().toISOString())
    .select("id")
    .maybeSingle();
  if (error) {
    console.error("obsidian_vault_complete_failed", error.code || "db_error");
    return NextResponse.json({ ok: false, error: "complete_failed" }, { status: 500 });
  }
  if (!data) return NextResponse.json({ ok: false, error: "request_not_processing" }, { status: 409 });
  return NextResponse.json({ ok: true, request_id: requestId }, { headers: { "Cache-Control": "no-store" } });
}
