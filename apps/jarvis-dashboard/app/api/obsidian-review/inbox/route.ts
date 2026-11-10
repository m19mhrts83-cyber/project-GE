import { timingSafeEqual as cryptoTimingSafeEqual } from "crypto";
import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";
export const maxDuration = 15;

function authorized(request: NextRequest): boolean {
  const expected = (process.env.OBSIDIAN_REVIEW_POLL_KEY || "").trim();
  if (!expected) return false;
  const supplied = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "").trim();
  const a = Buffer.from(expected);
  const b = Buffer.from(supplied);
  return a.length === b.length && cryptoTimingSafeEqual(a, b);
}

function unavailable() {
  return NextResponse.json({ ok: false, error: "review inbox is not configured" }, { status: 503 });
}

/** Mac-only pull endpoint. It never exposes pending reviews without the poll key. */
export async function GET(request: NextRequest) {
  if (!authorized(request)) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const limitRaw = Number(request.nextUrl.searchParams.get("limit") || "5");
  const limit = Number.isInteger(limitRaw) ? Math.max(1, Math.min(limitRaw, 10)) : 5;
  const supabase = createServiceClient();
  if (!supabase) return unavailable();
  let expiredCount = 0;
  if (request.nextUrl.searchParams.get("dryRun") !== "1") {
    // Keep the remote queue as a short-lived handoff, not a second journal.
    const expiry = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
    const { data: expired, error: expiryError } = await supabase
      .from("obsidian_review_inbox")
      .delete()
      .eq("status", "pending")
      .lt("created_at", expiry)
      .select("review_id");
    if (expiryError) {
      console.error("obsidian_review_expiry_cleanup_failed", expiryError.code || "db_error");
      return NextResponse.json({ ok: false, error: "inbox_cleanup_failed" }, { status: 500 });
    }
    expiredCount = expired?.length || 0;
  }
  const { data, error } = await supabase
    .from("obsidian_review_inbox")
    .select("review_id,review_date,raw_log,tactical_review,created_at")
    .eq("status", "pending")
    .order("created_at", { ascending: true })
    .limit(limit);
  if (error) {
    console.error("obsidian_review_poll_failed", error.code || "db_error");
    return NextResponse.json({ ok: false, error: "inbox_read_failed" }, { status: 500 });
  }
  return NextResponse.json(
    { ok: true, items: data || [], expired_count: expiredCount },
    { headers: { "Cache-Control": "no-store" } },
  );
}

/** Acknowledge only after local files and the existing OGD upload both succeed. */
export async function POST(request: NextRequest) {
  if (!authorized(request)) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  const reviewId = typeof body.review_id === "string" ? body.review_id.trim() : "";
  const paths = Array.isArray(body.saved_paths) ? body.saved_paths : [];
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(reviewId) ||
      paths.length !== 2 || paths.some((p) => typeof p !== "string" || !p.startsWith("01_Journaling/★Journal/日次レビュー/"))) {
    return NextResponse.json({ ok: false, error: "invalid_ack" }, { status: 400 });
  }
  const supabase = createServiceClient();
  if (!supabase) return unavailable();
  const { data, error } = await supabase
    .from("obsidian_review_inbox")
    .update({
      status: "delivered",
      delivered_at: new Date().toISOString(),
      saved_paths: paths,
      raw_log: null,
      tactical_review: null,
    })
    .eq("review_id", reviewId)
    .eq("status", "pending")
    .select("review_id")
    .maybeSingle();
  if (error) {
    console.error("obsidian_review_ack_failed", error.code || "db_error");
    return NextResponse.json({ ok: false, error: "ack_failed" }, { status: 500 });
  }
  if (!data) {
    const existing = await supabase.from("obsidian_review_inbox").select("status").eq("review_id", reviewId).maybeSingle();
    if (existing.data?.status === "delivered") return NextResponse.json({ ok: true, already_delivered: true });
    return NextResponse.json({ ok: false, error: "review_not_found" }, { status: 404 });
  }
  return NextResponse.json({ ok: true, review_id: reviewId });
}
