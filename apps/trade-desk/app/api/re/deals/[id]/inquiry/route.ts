import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

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
  const action = String(body.action || "");

  const { data: row, error: getErr } = await supabase
    .from("kurashift_re_deals")
    .select("id, title, status, summary_json")
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
      ? ({ ...(row.summary_json as Record<string, unknown>) } as Record<
          string,
          unknown
        >)
      : {};

  if (action === "send") {
    if (body.ui_confirmed !== true) {
      return NextResponse.json(
        { error: "ui_confirmed が必要です" },
        { status: 400 }
      );
    }
    const to = String(body.to || "").trim();
    const subject = String(body.subject || "").trim();
    const mailBody = String(body.body || "").trim();
    if (!to.includes("@") || !subject || !mailBody) {
      return NextResponse.json(
        { error: "to / subject / body が必要です" },
        { status: 400 }
      );
    }

    sj.inquiry_status = "draft";
    const now = new Date().toISOString();
    await supabase
      .from("kurashift_re_deals")
      .update({ summary_json: sj, updated_at: now })
      .eq("id", id);

    const { data: job, error: jobErr } = await supabase
      .from("kurashift_jobs")
      .insert({
        job_type: "re_deal_inquiry_send",
        title: `第一問い合わせ: ${String(row.title || "").slice(0, 60)}`,
        status: "queued",
        payload: {
          deal_id: id,
          to,
          subject,
          body: mailBody,
          ui_confirmed: true,
          ui_confirmed_at: now,
        },
        created_by: user.email ?? user.id,
      })
      .select("id")
      .single();
    if (jobErr) {
      return NextResponse.json({ error: jobErr.message }, { status: 500 });
    }
    return NextResponse.json({ ok: true, job_id: job?.id, inquiry_status: "draft" });
  }

  if (action === "build_ops_pack") {
    const { data: job, error: jobErr } = await supabase
      .from("kurashift_jobs")
      .insert({
        job_type: "re_deal_ops_pack",
        title: `運営相談パック: ${String(row.title || "").slice(0, 60)}`,
        status: "queued",
        payload: { deal_id: id },
        created_by: user.email ?? user.id,
      })
      .select("id")
      .single();
    if (jobErr) {
      return NextResponse.json({ error: jobErr.message }, { status: 500 });
    }
    return NextResponse.json({ ok: true, job_id: job?.id });
  }

  if (action === "poll") {
    const { data: job, error: jobErr } = await supabase
      .from("kurashift_jobs")
      .insert({
        job_type: "re_deal_inquiry_poll",
        title: `返信取込: ${String(row.title || "").slice(0, 60)}`,
        status: "queued",
        payload: { deal_id: id },
        created_by: user.email ?? user.id,
      })
      .select("id")
      .single();
    if (jobErr) {
      return NextResponse.json({ error: jobErr.message }, { status: 500 });
    }
    return NextResponse.json({ ok: true, job_id: job?.id });
  }

  return NextResponse.json(
    { error: "action must be send | build_ops_pack | poll" },
    { status: 400 }
  );
}
