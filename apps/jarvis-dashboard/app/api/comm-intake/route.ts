import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { actorForKey, bearerOf } from "@/lib/jobRecovery";
import { MAX_BODY_BYTES, PER_MINUTE, enqueue, recentCount, validateBody } from "@/lib/commIntake";

export const runtime = "nodejs";
export const maxDuration = 15;

/** 台帳の受付窓口。ボットが直接登録する（読み取りは不可。応答は件数と id だけ）。 */
export async function POST(request: NextRequest) {
  const actor = actorForKey(bearerOf(request.headers.get("authorization")), process.env.COMM_INTAKE_KEYS);
  if (!actor) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const raw = await request.text();
  if (Buffer.byteLength(raw, "utf8") > MAX_BODY_BYTES) {
    return NextResponse.json({ ok: false, error: "payload_too_large" }, { status: 413 });
  }
  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  const v = validateBody(body, actor);
  if (!v.ok) return NextResponse.json({ ok: false, error: v.error, index: v.index }, { status: 400 });
  const supabase = createServiceClient();
  if (!supabase) return NextResponse.json({ ok: false, error: "not_configured" }, { status: 503 });
  try {
    if ((await recentCount(supabase, actor)) + v.items.length > PER_MINUTE) {
      return NextResponse.json(
        { ok: false, error: "rate_limited", message: `1分あたり${PER_MINUTE}件までです` },
        { status: 429, headers: { "Retry-After": "60" } },
      );
    }
    const r = await enqueue(supabase, actor, v.items);
    return NextResponse.json(
      { ok: true, accepted: r.accepted, ids: r.ids },
      { status: r.created > 0 ? 202 : 200, headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    console.error("comm_intake_failed", error instanceof Error ? error.message : "error");
    return NextResponse.json({ ok: false, error: "intake_failed" }, { status: 500 });
  }
}
