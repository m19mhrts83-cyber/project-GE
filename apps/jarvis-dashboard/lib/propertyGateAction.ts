import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";

export type GateAction = "yes" | "no";

export function htmlPage(title: string, body: string, ok: boolean) {
  const color = ok ? "#065f46" : "#991b1b";
  return new NextResponse(
    `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<title>${title}</title>
<body style="font-family:system-ui;padding:2rem;max-width:36rem;color:${color}">
<h1 style="font-size:1.25rem">${title}</h1>
<pre style="white-space:pre-wrap;background:#f3f4f6;padding:1rem;border-radius:8px;color:#111">${body}</pre>
<p style="color:#6b7280;font-size:0.875rem">このタブは閉じて大丈夫です。結果は Slack #consult にも出ます。</p>
</body></html>`,
    {
      status: ok ? 200 : 400,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    },
  );
}

export function tokenOk(token: string | null | undefined): boolean {
  const expected = (process.env.PROPERTY_GATE_ACTION_TOKEN || "").trim();
  if (!expected) return false;
  const got = (token || "").trim();
  if (!got || got.length !== expected.length) return false;
  try {
    return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
  } catch {
    return false;
  }
}

/** 短縮 URL 用 HMAC（先頭10桁）。秘密は PROPERTY_GATE_ACTION_TOKEN。 */
export function actionSig(dealId: string, action: GateAction): string {
  const secret = (process.env.PROPERTY_GATE_ACTION_TOKEN || "").trim();
  return createHmac("sha256", secret)
    .update(`${dealId}:${action}`, "utf8")
    .digest("hex")
    .slice(0, 10);
}

export function sigOk(
  dealId: string,
  action: GateAction,
  sig: string | null | undefined,
): boolean {
  const expected = actionSig(dealId, action);
  const got = (sig || "").trim().toLowerCase();
  if (!got || got.length !== expected.length) return false;
  try {
    return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
  } catch {
    return false;
  }
}

export function parseAction(raw: string | null | undefined): GateAction | null {
  const a = (raw || "").trim().toLowerCase();
  if (a === "yes" || a === "y" || a === "進めて") return "yes";
  if (a === "no" || a === "n" || a === "見送り") return "no";
  return null;
}

export async function applyGate(
  dealId: string,
  action: GateAction,
  source: string,
): Promise<{ ok: boolean; message: string; job_id?: string }> {
  const sb = createServiceClient();
  if (!sb) {
    return { ok: false, message: "Service Role 未設定" };
  }

  const { data: row, error } = await sb
    .from("kurashift_re_deals")
    .select("id, title, inquiry_status, summary_json, status")
    .eq("id", dealId)
    .maybeSingle();
  if (error || !row) {
    return { ok: false, message: error?.message || "deal not found" };
  }

  const sj =
    row.summary_json && typeof row.summary_json === "object"
      ? ({ ...(row.summary_json as Record<string, unknown>) } as Record<
          string,
          unknown
        >)
      : {};
  const prevGate =
    sj.property_gate && typeof sj.property_gate === "object"
      ? (sj.property_gate as Record<string, unknown>)
      : {};
  const prevDecision = String(prevGate.decision || "");
  const inq = String(row.inquiry_status || sj.inquiry_status || "none");
  const now = new Date().toISOString();
  const title = String(row.title || "").slice(0, 60);
  const alreadySent =
    Boolean(sj.inquiry_sent_at) ||
    String(prevGate.send_result || "").includes("sent") ||
    Boolean(prevGate.gmail_id);

  if (action === "no") {
    if (prevDecision === "no") {
      return { ok: true, message: `既に見送り済: ${title}` };
    }
    sj.inquiry_status = "none";
    sj.property_gate = { ...prevGate, decision: "no", at: now, source };
    sj.auto_pass_reason = sj.auto_pass_reason || "property_gate_no";
    await sb
      .from("kurashift_re_deals")
      .update({
        status: "passed",
        inquiry_status: "none",
        summary_json: sj,
        updated_at: now,
      })
      .eq("id", dealId);
    return { ok: true, message: `見送りにしました: ${title}` };
  }

  // yes
  if (
    prevDecision === "yes" ||
    prevDecision === "sent" ||
    inq === "sending" ||
    inq === "awaiting_reply" ||
    inq === "has_reply" ||
    alreadySent
  ) {
    return {
      ok: true,
      message: `既に進行中/送信済 (inq=${inq}): ${title}`,
    };
  }

  const idempotencyKey = `${dealId}:first_inquiry`;
  const { data: existingJobs } = await sb
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
    return p.deal_id === dealId || p.idempotency_key === idempotencyKey;
  });
  if (dup) {
    return {
      ok: true,
      message: `送信ジョブ既存 (${dup.status}): ${title}`,
      job_id: String(dup.id),
    };
  }

  // handoff 誤ラベル修復
  if (inq === "awaiting_grok" && sj.awaiting_kurashift_first_inquiry) {
    sj.inquiry_status = "awaiting_first_inquiry";
  }

  sj.inquiry_status = "sending";
  sj.property_gate = { ...prevGate, decision: "yes", at: now, source };
  await sb
    .from("kurashift_re_deals")
    .update({
      inquiry_status: "sending",
      summary_json: sj,
      updated_at: now,
    })
    .eq("id", dealId);

  const { data: job, error: jobErr } = await sb
    .from("kurashift_jobs")
    .insert({
      job_type: "re_deal_inquiry_send",
      title: `第一問合せ(Slackゲート): ${title}`,
      status: "queued",
      payload: {
        deal_id: dealId,
        ui_confirmed: true,
        ui_confirmed_at: now,
        slack_gate_yes: true,
        confirm_source: source,
        idempotency_key: idempotencyKey,
      },
      created_by: "slack_consult_action",
    })
    .select("id")
    .single();

  if (jobErr) {
    return { ok: false, message: jobErr.message };
  }
  return {
    ok: true,
    message: `問合せ送信をキューしました: ${title}`,
    job_id: job?.id ? String(job.id) : undefined,
  };
}
