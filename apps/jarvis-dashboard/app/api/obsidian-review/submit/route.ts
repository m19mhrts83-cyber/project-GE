import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { enqueueDailyReview, submitKeyMatches, validateDailyReview } from "@/lib/obsidianReviewInbox";

export const runtime = "nodejs";
export const maxDuration = 15;
const MAX_BODY_BYTES = 768 * 1024;

/** Bearer-authenticated endpoint for a ChatGPT Sites plugin or API Action. */
export async function POST(request: NextRequest) {
  const bearer = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "") || "";
  if (!submitKeyMatches(bearer)) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  const raw = await request.text();
  if (Buffer.byteLength(raw, "utf8") > MAX_BODY_BYTES) {
    return NextResponse.json({ ok: false, error: "payload_too_large" }, { status: 413 });
  }
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  const validated = validateDailyReview(body);
  if (!validated.ok) return NextResponse.json({ ok: false, error: validated.error }, { status: 400 });
  const supabase = createServiceClient();
  if (!supabase) return NextResponse.json({ ok: false, error: "review_inbox_not_configured" }, { status: 503 });
  try {
    const result = await enqueueDailyReview(supabase, validated.value);
    return NextResponse.json(
      { ok: true, ...result, review_id: validated.value.review_id },
      { status: result.duplicate ? 200 : 202, headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    const code = error instanceof Error ? error.message : "db_error";
    console.error("obsidian_review_submit_failed", code);
    return NextResponse.json({ ok: false, error: "review_could_not_be_queued" }, { status: 500 });
  }
}
