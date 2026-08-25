import { createClient } from "@/lib/supabase/server";
import {
  buildTier2QueueFromDeals,
  countTodayInquirySends,
  isTier2Enabled,
} from "@/lib/reInquiryTier2Queue";
import {
  evaluateInquiryCandidate,
  type ReDealForInquiry,
} from "@/lib/reInquiryCandidate";
import { loadInquiryAutoConfig } from "@/lib/reInquiryAutoConfig";
import {
  checkFingerprintSendGuard,
  resolveDealFingerprint,
} from "@/lib/reDealFingerprintGuard";
import { createHash } from "crypto";
import { NextResponse } from "next/server";

function bodySha256(body: string): string {
  return createHash("sha256").update(body, "utf8").digest("hex");
}

type SendItem = {
  deal_id: string;
  to: string;
  subject: string;
  body: string;
  confirm_snapshot: { to: string; subject: string; body_sha256: string };
};

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const cfg = loadInquiryAutoConfig();
  if (!isTier2Enabled(cfg)) {
    return NextResponse.json(
      { error: "Tier2 は無効です（kurashift_re_inquiry_auto.yaml）" },
      { status: 403 }
    );
  }

  const payload = await req.json().catch(() => ({}));
  if (payload.ui_confirmed !== true) {
    return NextResponse.json(
      { error: "ui_confirmed が必要です" },
      { status: 400 }
    );
  }

  const items = Array.isArray(payload.items) ? (payload.items as SendItem[]) : [];
  if (items.length === 0) {
    return NextResponse.json({ error: "items が空です" }, { status: 400 });
  }

  const dailyCap = cfg.daily_send_cap ?? 5;
  const sentToday = await countTodayInquirySends(supabase);
  const remaining = dailyCap - sentToday;
  if (remaining <= 0) {
    return NextResponse.json(
      {
        error: `本日の送信上限（${dailyCap}件）に達しています`,
        sent_today: sentToday,
      },
      { status: 429 }
    );
  }
  if (items.length > remaining) {
    return NextResponse.json(
      {
        error: `残り ${remaining} 件まで送信できます（選択 ${items.length} 件）`,
        remaining,
      },
      { status: 400 }
    );
  }

  const dealIds = items.map((i) => String(i.deal_id || "")).filter(Boolean);
  const { data: deals, error: dealsErr } = await supabase
    .from("kurashift_re_deals")
    .select(
      "id, title, area, price_man, status, source, match_score, inquiry_status, summary_json, property_fingerprint"
    )
    .in("id", dealIds);
  if (dealsErr) {
    return NextResponse.json({ error: dealsErr.message }, { status: 500 });
  }

  const dealMap = new Map(
    (deals || []).map((d) => [String(d.id), d as ReDealForInquiry])
  );
  const allowedIds = new Set(
    buildTier2QueueFromDeals(Array.from(dealMap.values()), cfg).map(
      (q) => q.deal_id
    )
  );

  const jobIds: string[] = [];
  const errors: string[] = [];
  const now = new Date().toISOString();

  for (const item of items) {
    const dealId = String(item.deal_id || "");
    const deal = dealMap.get(dealId);
    if (!deal) {
      errors.push(`${dealId}: not found`);
      continue;
    }
    if (!allowedIds.has(dealId)) {
      errors.push(`${dealId}: Tier2 キュー対象外`);
      continue;
    }

    const evalInq = evaluateInquiryCandidate(deal, cfg);
    if (!evalInq.tier2) {
      errors.push(`${dealId}: Tier2 条件を満たしません`);
      continue;
    }

    const to = String(item.to || "").trim();
    const subject = String(item.subject || "").trim();
    const mailBody = String(item.body || "").trim();
    if (!to.includes("@") || !subject || !mailBody) {
      errors.push(`${dealId}: to/subject/body 不足`);
      continue;
    }

    const snap = item.confirm_snapshot;
    const hash = bodySha256(mailBody);
    if (
      !snap ||
      String(snap.to).trim() !== to ||
      String(snap.subject).trim() !== subject ||
      String(snap.body_sha256).trim() !== hash
    ) {
      errors.push(`${dealId}: confirm_snapshot 不一致`);
      continue;
    }

    const inquiryStatus =
      String(deal.inquiry_status || "none") || "none";
    if (
      inquiryStatus === "sending" ||
      inquiryStatus === "awaiting_reply" ||
      inquiryStatus === "has_reply"
    ) {
      errors.push(`${dealId}: 問合せ進行中 (${inquiryStatus})`);
      continue;
    }

    const sj =
      deal.summary_json && typeof deal.summary_json === "object"
        ? ({ ...(deal.summary_json as Record<string, unknown>) } as Record<
            string,
            unknown
          >)
        : {};

    const fpGuard = await checkFingerprintSendGuard(supabase, {
      id: dealId,
      title: deal.title,
      area: (deal as { area?: string | null }).area ?? null,
      price_man: (deal as { price_man?: number | null }).price_man ?? null,
      status: deal.status,
      source: (deal as { source?: string | null }).source ?? null,
      inquiry_status: inquiryStatus,
      summary_json: sj,
      property_fingerprint:
        (deal as { property_fingerprint?: string | null })
          .property_fingerprint ?? null,
    });
    if (fpGuard.blocked) {
      errors.push(
        `${dealId}: fingerprint block (${fpGuard.reason}` +
          (fpGuard.sibling_deal_id
            ? `; sibling=${fpGuard.sibling_deal_id}`
            : "") +
          `)`
      );
      continue;
    }

    const fingerprint =
      fpGuard.fingerprint ||
      resolveDealFingerprint({
        id: dealId,
        title: deal.title,
        area: (deal as { area?: string | null }).area ?? null,
        price_man: (deal as { price_man?: number | null }).price_man ?? null,
        summary_json: sj,
        property_fingerprint:
          (deal as { property_fingerprint?: string | null })
            .property_fingerprint ?? null,
      });
    sj.inquiry_status = "draft";
    sj.property_fingerprint = fingerprint;

    await supabase
      .from("kurashift_re_deals")
      .update({
        inquiry_status: "draft",
        summary_json: sj,
        updated_at: now,
        property_fingerprint: fingerprint,
      })
      .eq("id", dealId);

    const idempotencyKey = `${dealId}:first_inquiry`;
    const { data: job, error: jobErr } = await supabase
      .from("kurashift_jobs")
      .insert({
        job_type: "re_deal_inquiry_send",
        title: `第一問い合わせ(Tier2): ${String(deal.title || "").slice(0, 50)}`,
        status: "queued",
        payload: {
          deal_id: dealId,
          to,
          subject,
          body: mailBody,
          ui_confirmed: true,
          ui_confirmed_at: now,
          tier2_batch: true,
          confirm_snapshot: { to, subject, body_sha256: hash },
          idempotency_key: idempotencyKey,
        },
        created_by: user.email ?? user.id,
      })
      .select("id")
      .single();

    if (jobErr) {
      errors.push(`${dealId}: ${jobErr.message}`);
    } else if (job?.id) {
      jobIds.push(job.id);
    }
  }

  return NextResponse.json({
    ok: errors.length === 0,
    enqueued: jobIds.length,
    job_ids: jobIds,
    errors,
    sent_today: sentToday + jobIds.length,
    daily_cap: dailyCap,
  });
}

/** プレビュー全文取得（バッチ画面用） */
export async function GET() {
  return NextResponse.json(
    { error: "POST only. Preview via /api/re/inquiry-tier2-queue" },
    { status: 405 }
  );
}
