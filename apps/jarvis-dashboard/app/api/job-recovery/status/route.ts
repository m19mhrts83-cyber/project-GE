import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";
import {
  RECOVERY_JOBS,
  actorForKey,
  bearerOf,
  decideRecovery,
  githubConfigured,
  lockFree,
  readHeartbeats,
  recentRuns,
} from "@/lib/jobRecovery";

export const runtime = "nodejs";
export const maxDuration = 20;

/** 状態の確認口（読み取り専用）。ホーク・番頭さんの窓口用の鍵で読む。 */
export async function GET(request: NextRequest) {
  const actor = actorForKey(bearerOf(request.headers.get("authorization")));
  if (!actor) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const supabase = createServiceClient();
  if (!supabase) return NextResponse.json({ ok: false, error: "not_configured" }, { status: 503 });
  const now = new Date();
  try {
    const hb = await readHeartbeats(supabase);
    const jobs = await Promise.all(
      Object.values(RECOVERY_JOBS).map(async (job) => {
        let runs: Awaited<ReturnType<typeof recentRuns>> = [];
        let runsError: string | null = null;
        if (githubConfigured()) {
          try {
            runs = await recentRuns(job.workflow, 5);
          } catch (e) {
            runsError = e instanceof Error ? e.message : "github_error";
          }
        } else {
          runsError = "github_not_configured";
        }
        const lock = hb[`recovery_lock:${job.id}`] || null;
        const decision = runsError ? null : decideRecovery(runs);
        return {
          job: job.id,
          label: job.label,
          last_ok: hb[`job_ok:${job.id}`] || null,
          backup_ok: job.id === "comm_write" ? hb["job_ok:comm_write_backup"] || null : undefined,
          recent_runs: runs.slice(0, 3),
          runs_error: runsError,
          lock,
          can_rerun: Boolean(decision?.ok) && lockFree(lock?.at || null, now),
          blocked_reason: decision && !decision.ok ? decision.message : null,
        };
      }),
    );
    return NextResponse.json(
      { ok: true, viewer: actor, now: now.toISOString(), jobs },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    console.error("job_recovery_status_failed", error instanceof Error ? error.message : "error");
    return NextResponse.json({ ok: false, error: "status_failed" }, { status: 500 });
  }
}
