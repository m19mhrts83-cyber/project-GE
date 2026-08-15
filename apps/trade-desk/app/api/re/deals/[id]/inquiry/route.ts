import { createClient } from "@/lib/supabase/server";
import { createHash } from "crypto";
import { NextResponse } from "next/server";

function bodySha256(body: string): string {
  return createHash("sha256").update(body, "utf8").digest("hex");
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
  const action = String(body.action || "");

  const { data: row, error: getErr } = await supabase
    .from("kurashift_re_deals")
    .select("id, title, status, summary_json, inquiry_status")
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
  const inquiryStatus =
    String(row.inquiry_status || sj.inquiry_status || "none") || "none";

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

    const snap =
      body.confirm_snapshot && typeof body.confirm_snapshot === "object"
        ? (body.confirm_snapshot as Record<string, unknown>)
        : null;
    if (!snap) {
      return NextResponse.json(
        { error: "confirm_snapshot が必要です" },
        { status: 400 }
      );
    }
    const snapTo = String(snap.to || "").trim();
    const snapSubject = String(snap.subject || "").trim();
    const snapHash = String(snap.body_sha256 || "").trim();
    const hash = bodySha256(mailBody);
    if (snapTo !== to || snapSubject !== subject || snapHash !== hash) {
      return NextResponse.json(
        { error: "confirm_snapshot が本文と一致しません。確認画面からやり直してください" },
        { status: 400 }
      );
    }

    if (
      inquiryStatus === "sending" ||
      inquiryStatus === "awaiting_reply" ||
      inquiryStatus === "has_reply"
    ) {
      return NextResponse.json(
        { error: "既に問い合わせ進行中です", inquiry_status: inquiryStatus },
        { status: 409 }
      );
    }

    const idempotencyKey = `${id}:first_inquiry`;
    const { data: existingJobs } = await supabase
      .from("kurashift_jobs")
      .select("id, status, payload")
      .eq("job_type", "re_deal_inquiry_send")
      .in("status", ["queued", "running", "succeeded"])
      .order("created_at", { ascending: false })
      .limit(40);

    const dup = (existingJobs || []).find((j) => {
      const p =
        j.payload && typeof j.payload === "object"
          ? (j.payload as Record<string, unknown>)
          : {};
      return (
        p.deal_id === id ||
        p.idempotency_key === idempotencyKey
      );
    });
    if (dup) {
      return NextResponse.json(
        {
          error: "同一案件の送信ジョブが既にあります",
          job_id: dup.id,
          job_status: dup.status,
        },
        { status: 409 }
      );
    }

    sj.inquiry_status = "draft";
    const now = new Date().toISOString();
    const { error: draftErr } = await supabase
      .from("kurashift_re_deals")
      .update({
        inquiry_status: "draft",
        summary_json: sj,
        updated_at: now,
      })
      .eq("id", id);
    if (draftErr) {
      await supabase
        .from("kurashift_re_deals")
        .update({ summary_json: sj, updated_at: now })
        .eq("id", id);
    }

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
          confirm_snapshot: { to, subject, body_sha256: hash },
          idempotency_key: idempotencyKey,
        },
        created_by: user.email ?? user.id,
      })
      .select("id")
      .single();
    if (jobErr) {
      return NextResponse.json({ error: jobErr.message }, { status: 500 });
    }
    return NextResponse.json({
      ok: true,
      job_id: job?.id,
      inquiry_status: "draft",
    });
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

  if (action === "autopass_confirm" || action === "autopass_reject") {
    const reason =
      typeof sj.auto_pass_reason === "string" ? sj.auto_pass_reason : "unknown";
    const { data: learn } = await supabase
      .from("kurashift_auto_pass_learn")
      .select("reason, confirm_count, reject_count")
      .eq("reason", reason)
      .maybeSingle();

    if (action === "autopass_confirm") {
      const confirmCount = (learn?.confirm_count || 0) + 1;
      const rejectCount = learn?.reject_count || 0;
      const allowlisted =
        confirmCount >= 3 && rejectCount === 0
          ? new Date().toISOString()
          : null;
      await supabase.from("kurashift_auto_pass_learn").upsert({
        reason,
        confirm_count: confirmCount,
        reject_count: rejectCount,
        allowlisted_at: allowlisted,
        updated_at: new Date().toISOString(),
      });
      sj.auto_pass_pending_read = false;
      sj.auto_pass_reviewed = "confirm";
      await supabase
        .from("kurashift_re_deals")
        .update({ summary_json: sj, updated_at: new Date().toISOString() })
        .eq("id", id);
      const { data: job } = await supabase
        .from("kurashift_jobs")
        .insert({
          job_type: "re_deal_mark_gmail_read",
          title: `自動見送り既読確認: ${String(row.title || "").slice(0, 50)}`,
          status: "queued",
          payload: { deal_id: id },
          created_by: user.email ?? user.id,
        })
        .select("id")
        .single();
      return NextResponse.json({
        ok: true,
        action: "autopass_confirm",
        job_id: job?.id,
        reason,
        confirm_count: confirmCount,
      });
    }

    // reject → info に戻し、学習カウントリセット寄り
    await supabase.from("kurashift_auto_pass_learn").upsert({
      reason,
      confirm_count: 0,
      reject_count: (learn?.reject_count || 0) + 1,
      allowlisted_at: null,
      updated_at: new Date().toISOString(),
    });
    sj.auto_pass_pending_read = false;
    sj.auto_pass_reviewed = "reject";
    delete sj.auto_pass_at_ingest;
    await supabase
      .from("kurashift_re_deals")
      .update({
        status: "info",
        summary_json: sj,
        updated_at: new Date().toISOString(),
      })
      .eq("id", id);
    return NextResponse.json({ ok: true, action: "autopass_reject", reason });
  }

  return NextResponse.json(
    {
      error:
        "action must be send | build_ops_pack | poll | autopass_confirm | autopass_reject",
    },
    { status: 400 }
  );
}
