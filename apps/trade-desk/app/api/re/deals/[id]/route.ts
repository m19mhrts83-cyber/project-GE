import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

type Action = "confirm" | "pass";

const KEEP_ON_CONFIRM = new Set([
  "viewing",
  "offer",
  "loan",
  "purchased",
]);

function nextStatus(action: Action, current: string): string {
  if (action === "pass") return "passed";
  if (KEEP_ON_CONFIRM.has(current)) return current;
  // info / passed / その他 → 内見レーンへ
  return "viewing";
}

export async function POST(
  req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const action = String(body.action || "") as Action;
  if (action !== "confirm" && action !== "pass") {
    return NextResponse.json(
      { error: "action must be confirm | pass" },
      { status: 400 }
    );
  }

  const { data: row, error: getErr } = await supabase
    .from("kurashift_re_deals")
    .select("id, title, status, source, summary_json")
    .eq("id", id)
    .maybeSingle();
  if (getErr || !row) {
    return NextResponse.json(
      { error: getErr?.message || "not found" },
      { status: 404 }
    );
  }

  const sj =
    row.summary_json && typeof row.summary_json === "object"
      ? (row.summary_json as Record<string, unknown>)
      : {};
  const gmailId = typeof sj.gmail_id === "string" ? sj.gmail_id : null;
  const alreadyRead =
    typeof sj.gmail_read_at === "string" && sj.gmail_read_at.length > 0;

  const status = nextStatus(action, String(row.status || "info"));
  const now = new Date().toISOString();

  const { data: updated, error: upErr } = await supabase
    .from("kurashift_re_deals")
    .update({ status, updated_at: now })
    .eq("id", id)
    .select("id, title, status, source")
    .single();
  if (upErr || !updated) {
    return NextResponse.json(
      { error: upErr?.message || "update failed" },
      { status: 500 }
    );
  }

  let mark_read_queued = false;
  let mark_read_skipped: string | null = null;
  let job_id: string | null = null;

  if (!gmailId) {
    mark_read_skipped = "no_gmail_id";
  } else if (alreadyRead) {
    mark_read_skipped = "already_read";
  } else {
    const jobTitle =
      action === "confirm"
        ? `Gmail既読（確認）: ${String(row.title || "").slice(0, 60)}`
        : `Gmail既読（対象外）: ${String(row.title || "").slice(0, 60)}`;
    const { data: job, error: jobErr } = await supabase
      .from("kurashift_jobs")
      .insert({
        job_type: "re_deal_mark_gmail_read",
        title: jobTitle,
        status: "queued",
        payload: {
          deal_id: id,
          action,
          gmail_id: gmailId,
          source: row.source || sj.account || null,
        },
        created_by: user.email ?? user.id,
      })
      .select("id")
      .single();
    if (jobErr) {
      return NextResponse.json(
        {
          ok: true,
          deal: updated,
          mark_read_queued: false,
          mark_read_skipped: null,
          warning: `status更新済・既読ジョブ失敗: ${jobErr.message}`,
        },
        { status: 200 }
      );
    }
    mark_read_queued = true;
    job_id = job?.id ?? null;
  }

  return NextResponse.json({
    ok: true,
    deal: updated,
    mark_read_queued,
    mark_read_skipped,
    job_id,
  });
}
