import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";
import {
  LOCK_HOURS,
  RECOVERY_JOBS,
  acquireLock,
  actorForKey,
  bearerOf,
  decideRecovery,
  dispatch,
  githubConfigured,
  jobById,
  jstLabel,
  postHub,
  recentRuns,
  releaseLock,
} from "@/lib/jobRecovery";

export const runtime = "nodejs";
export const maxDuration = 20;

/** 再実行の窓口。許可した4本だけ。同じジョブは6時間に1回まで。受付を #ai-hub に1行。 */
export async function POST(request: NextRequest) {
  const actor = actorForKey(bearerOf(request.headers.get("authorization")));
  if (!actor) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  let body: { job?: unknown; reason?: unknown } = {};
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  const job = jobById(body.job);
  if (!job) {
    return NextResponse.json(
      { ok: false, error: "job_not_allowed", allowed: Object.keys(RECOVERY_JOBS) },
      { status: 400 },
    );
  }
  const reason = typeof body.reason === "string" ? body.reason.replace(/\s+/g, " ").slice(0, 80) : "";
  const supabase = createServiceClient();
  if (!supabase || !githubConfigured()) {
    return NextResponse.json({ ok: false, error: "not_configured" }, { status: 503 });
  }
  const now = new Date();
  try {
    const decision = decideRecovery(await recentRuns(job.workflow, 5));
    if (!decision.ok) {
      await postHub(`🔧 再実行 見送り｜${job.id}｜${actor}｜${jstLabel(now)}｜${decision.message}`);
      return NextResponse.json({ ok: false, error: decision.reason, message: decision.message }, { status: 409 });
    }
    if (!(await acquireLock(supabase, job.id, actor, now))) {
      return NextResponse.json(
        { ok: false, error: "rate_limited", message: `同じジョブは${LOCK_HOURS}時間に1回までです` },
        { status: 429 },
      );
    }
    try {
      await dispatch(job, actor);
    } catch (e) {
      await releaseLock(supabase, job.id);
      throw e;
    }
    await postHub(
      `🔧 再実行 受付｜${job.id}（${job.label}）｜${actor}｜${jstLabel(now)}${reason ? `｜${reason}` : ""}`,
    );
    return NextResponse.json({ ok: true, job: job.id, actor, accepted_at: now.toISOString() }, { status: 202 });
  } catch (error) {
    const code = error instanceof Error ? error.message : "error";
    console.error("job_recovery_run_failed", code);
    return NextResponse.json({ ok: false, error: "run_failed", detail: code.slice(0, 60) }, { status: 502 });
  }
}
