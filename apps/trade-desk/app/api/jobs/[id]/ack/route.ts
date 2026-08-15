import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { USER_VISIBLE_FAIL_JOB_TYPES } from "@/lib/jobFailVisibility";

type Ctx = { params: Promise<{ id: string }> };

/**
 * 失敗ジョブをユーザーが「確認した」と記録（result マージ。worker 上書き耐性は worker 側でも保持）。
 */
export async function POST(_req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { data: job, error } = await supabase
    .from("kurashift_jobs")
    .select("id, job_type, status, result")
    .eq("id", id)
    .maybeSingle();

  if (error || !job) {
    return NextResponse.json({ error: error?.message || "not found" }, { status: 404 });
  }

  const allow = new Set<string>(USER_VISIBLE_FAIL_JOB_TYPES);
  if (!allow.has(job.job_type)) {
    return NextResponse.json(
      { error: "このジョブ種別は確認対象外です" },
      { status: 400 }
    );
  }
  if (job.status !== "failed") {
    return NextResponse.json(
      { error: "failed のジョブのみ確認できます", status: job.status },
      { status: 409 }
    );
  }

  const prev =
    job.result && typeof job.result === "object" && !Array.isArray(job.result)
      ? { ...(job.result as Record<string, unknown>) }
      : {};
  const next = {
    ...prev,
    user_acked_at: new Date().toISOString(),
    user_acked_by: user.email ?? user.id,
  };

  const { error: upErr } = await supabase
    .from("kurashift_jobs")
    .update({ result: next })
    .eq("id", id);

  if (upErr) {
    return NextResponse.json({ error: upErr.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, job_id: id });
}
