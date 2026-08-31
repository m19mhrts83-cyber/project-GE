import { createClient } from "@/lib/supabase/server";
import { createHash } from "crypto";
import { NextResponse } from "next/server";
import {
  classifyInquiryChannel,
  isSelfEmail,
  selfEmailsExtraFromEnv,
} from "@/lib/reInquiryChannel";
import {
  checkFingerprintSendGuard,
  resolveDealFingerprint,
} from "@/lib/reDealFingerprintGuard";
import {
  buildInquiryPreviewFromTemplate,
  DEFAULT_RE_INQUIRY_TEMPLATE,
} from "@/lib/reInquiryShared";

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
    .select(
      "id, title, area, price_man, status, source, summary_json, inquiry_status, property_fingerprint"
    )
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

    const channelInfo = classifyInquiryChannel({
      title: String(row.title || ""),
      source: row.source != null ? String(row.source) : null,
      summaryJson: sj,
      explicitTo: to,
    });
    if (channelInfo.channel === "not_applicable") {
      return NextResponse.json(
        {
          error:
            "この案件は第一問合せ対象外です（Grok調査メモ／業者開拓メモ等）",
          inquiry_channel: channelInfo.channel,
        },
        { status: 400 }
      );
    }
    const inquiryChannel =
      String(body.inquiry_channel || "") === "grok_handoff" ||
      String(body.inquiry_channel || "") === "agent_email"
        ? String(body.inquiry_channel)
        : channelInfo.channel;
    const handoff = inquiryChannel === "grok_handoff";
    if (
      !handoff &&
      isSelfEmail(to, selfEmailsExtraFromEnv())
    ) {
      return NextResponse.json(
        {
          error:
            "仲介向け問合せの宛先が自己アドレスです。To を修正するか Grok 依頼に切り替えてください",
        },
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
      inquiryStatus === "awaiting_grok" ||
      inquiryStatus === "has_reply"
    ) {
      return NextResponse.json(
        { error: "既に問い合わせ進行中です", inquiry_status: inquiryStatus },
        { status: 409 }
      );
    }

    const fpGuard = await checkFingerprintSendGuard(supabase, {
      id: String(row.id),
      title: row.title != null ? String(row.title) : null,
      area: (row as { area?: string | null }).area ?? null,
      price_man: (row as { price_man?: number | null }).price_man ?? null,
      status: row.status != null ? String(row.status) : null,
      source: row.source != null ? String(row.source) : null,
      inquiry_status: inquiryStatus,
      summary_json: sj,
      property_fingerprint:
        (row as { property_fingerprint?: string | null }).property_fingerprint ??
        null,
    });
    if (fpGuard.blocked) {
      return NextResponse.json(
        {
          error: fpGuard.reason,
          property_fingerprint: fpGuard.fingerprint,
          sibling_deal_id: fpGuard.sibling_deal_id,
          sibling_inquiry_status: fpGuard.sibling_inquiry_status,
          sibling_job_id: fpGuard.sibling_job_id,
          sibling_job_status: fpGuard.sibling_job_status,
        },
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

    const fingerprint = fpGuard.fingerprint || resolveDealFingerprint({
      id: String(row.id),
      title: row.title != null ? String(row.title) : null,
      area: (row as { area?: string | null }).area ?? null,
      price_man: (row as { price_man?: number | null }).price_man ?? null,
      summary_json: sj,
      property_fingerprint:
        (row as { property_fingerprint?: string | null }).property_fingerprint ??
        null,
    });
    sj.inquiry_status = "sending";
    sj.property_fingerprint = fingerprint;
    const now = new Date().toISOString();
    const draftPatch: Record<string, unknown> = {
      inquiry_status: "sending",
      summary_json: sj,
      updated_at: now,
      property_fingerprint: fingerprint,
    };
    const { error: draftErr } = await supabase
      .from("kurashift_re_deals")
      .update(draftPatch)
      .eq("id", id);
    if (draftErr) {
      const soft: Record<string, unknown> = {
        summary_json: sj,
        updated_at: now,
      };
      if (!/property_fingerprint|column/i.test(String(draftErr.message))) {
        soft.inquiry_status = "sending";
      }
      await supabase.from("kurashift_re_deals").update(soft).eq("id", id);
    }

    const { data: job, error: jobErr } = await supabase
      .from("kurashift_jobs")
      .insert({
        job_type: "re_deal_inquiry_send",
        title: handoff
          ? `Grok問合せ依頼: ${String(row.title || "").slice(0, 60)}`
          : `第一問い合わせ: ${String(row.title || "").slice(0, 60)}`,
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
          inquiry_channel: inquiryChannel,
          handoff,
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
      inquiry_status: "sending",
      inquiry_channel: inquiryChannel,
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

  if (action === "form_draft") {
    const { data: job, error: jobErr } = await supabase
      .from("kurashift_jobs")
      .insert({
        job_type: "re_ops_form_draft",
        title: `運営相談フォーム下書き: ${String(row.title || "").slice(0, 50)}`,
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

  if (action === "kamiooya_form_submitted") {
    const channelInfo = classifyInquiryChannel({
      title: String(row.title || ""),
      source: row.source != null ? String(row.source) : null,
      summaryJson: sj,
    });
    if (channelInfo.channel !== "kamiooya_form") {
      return NextResponse.json(
        { error: "神大家紹介フォーム対象の案件ではありません" },
        { status: 400 }
      );
    }
    if (
      inquiryStatus === "awaiting_reply" ||
      inquiryStatus === "has_reply" ||
      inquiryStatus === "sending"
    ) {
      return NextResponse.json(
        { error: "既に問い合わせ進行中です", inquiry_status: inquiryStatus },
        { status: 409 }
      );
    }
    const now = new Date().toISOString();
    const nextSj = {
      ...sj,
      inquiry_status: "awaiting_reply",
      kamiooya_form_submitted_at: now,
      kamiooya_form_submitted_by: user.email ?? user.id,
    };
    const { error: upErr } = await supabase
      .from("kurashift_re_deals")
      .update({
        inquiry_status: "awaiting_reply",
        summary_json: nextSj,
        updated_at: now,
      })
      .eq("id", id);
    if (upErr) {
      return NextResponse.json({ error: upErr.message }, { status: 500 });
    }
    await supabase.from("kurashift_re_deal_events").insert({
      deal_id: id,
      event_type: "inquiry_kamiooya_form",
      from_status: String(row.status || "info"),
      to_status: String(row.status || "info"),
      actor: "user",
      summary: "神大家紹介フォーム送信済",
      payload: { action: "kamiooya_form_submitted" },
    });
    return NextResponse.json({
      ok: true,
      inquiry_status: "awaiting_reply",
      inquiry_channel: "kamiooya_form",
    });
  }

  if (action === "listing_web_submit") {
    const channelInfo = classifyInquiryChannel({
      title: String(row.title || ""),
      source: row.source != null ? String(row.source) : null,
      summaryJson: sj,
    });
    if (channelInfo.channel !== "listing_web") {
      return NextResponse.json(
        {
          error:
            "掲載ページ問合せ対象ではありません（Grok調査＋掲載URLが必要）",
          inquiry_channel: channelInfo.channel,
        },
        { status: 400 }
      );
    }
    if (
      inquiryStatus === "awaiting_reply" ||
      inquiryStatus === "has_reply" ||
      inquiryStatus === "sending"
    ) {
      return NextResponse.json(
        { error: "既に問い合わせ進行中です", inquiry_status: inquiryStatus },
        { status: 409 }
      );
    }
    const preview = buildInquiryPreviewFromTemplate(DEFAULT_RE_INQUIRY_TEMPLATE, {
      title: String(row.title || ""),
      summaryJson: sj,
      source: row.source != null ? String(row.source) : null,
      area: (row as { area?: string | null }).area ?? null,
      priceMan: (row as { price_man?: number | null }).price_man ?? null,
      dealId: id,
      signatureName:
        process.env.RE_INQUIRY_SIGNATURE_NAME ||
        process.env.PERSONAL_NAME ||
        "",
    });
    const listingUrl = String(
      (preview as { listing_url?: string }).listing_url ||
        channelInfo.to ||
        ""
    ).trim();
    const bodyText = String(preview.body || "").trim();
    if (!listingUrl || !bodyText) {
      return NextResponse.json(
        { error: "掲載URLまたは定型文が空です" },
        { status: 400 }
      );
    }
    const now = new Date().toISOString();
    const nextSj = {
      ...sj,
      inquiry_status: "awaiting_reply",
      inquiry_channel: "listing_web",
      listing_web_submitted_at: now,
      listing_web_submitted_by: user.email ?? user.id,
      listing_web_url: listingUrl,
    };
    const { error: upErr } = await supabase
      .from("kurashift_re_deals")
      .update({
        inquiry_status: "awaiting_reply",
        summary_json: nextSj,
        updated_at: now,
      })
      .eq("id", id);
    if (upErr) {
      return NextResponse.json({ error: upErr.message }, { status: 500 });
    }
    await supabase.from("kurashift_re_deal_events").insert({
      deal_id: id,
      event_type: "inquiry_listing_web",
      from_status: String(row.status || "info"),
      to_status: String(row.status || "info"),
      actor: "user",
      summary: "掲載ページで問合せ（定型文コピー）",
      payload: {
        action: "listing_web_submit",
        listing_url: listingUrl,
        inquiry_status: "awaiting_reply",
      },
    });
    return NextResponse.json({
      ok: true,
      inquiry_status: "awaiting_reply",
      inquiry_channel: "listing_web",
      listing_url: listingUrl,
      subject: preview.subject,
      body: bodyText,
    });
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
        "action must be send | build_ops_pack | form_draft | kamiooya_form_submitted | listing_web_submit | poll | autopass_confirm | autopass_reject",
    },
    { status: 400 }
  );
}
