/**
 * 物件第一問合せ — Mac worker が拾えないときの Vercel 冗長送信。
 * AI/LLM なし。定型テンプレ＋Gmail API。二重送信は job CAS＋inquiry_status。
 * 311 フルは Mac。ここは誤送の最小ゲート（self / 運営宛）。
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { sendGmailViaEnv } from "@/lib/gmail/sendFromEnv";
import { isSelfEmail, parseEmailAddr } from "@/lib/selfEmails";

const STALE_MS = 5 * 60 * 1000;
const KAMIOOYA_OPS = new Set([
  "support@kamiooya.com",
  "info@kamiooya.com",
  "noreply@kamiooya.com",
]);

function sb(): SupabaseClient | null {
  const url = (
    process.env.JARVIS_SUPABASE_URL ||
    process.env.NEXT_PUBLIC_SUPABASE_URL ||
    ""
  ).trim();
  // Vercel 本番は JARVIS_SUPABASE_SECRET_KEY（SERVICE_ROLE 別名）が多い
  const key = (
    process.env.JARVIS_SUPABASE_SERVICE_ROLE_KEY ||
    process.env.JARVIS_SUPABASE_SECRET_KEY ||
    ""
  ).trim();
  if (!url || !key) return null;
  return createClient(url, key, { auth: { persistSession: false } });
}

function isKamiooyaOps(email: string): boolean {
  const a = parseEmailAddr(email) || email.trim().toLowerCase();
  if (!a) return false;
  if (KAMIOOYA_OPS.has(a)) return true;
  if (a.endsWith("@kamiooya.com") || a.endsWith("@kamiooya.jp")) return true;
  return false;
}

function resolveTo(sj: Record<string, unknown>): string {
  for (const k of ["contact_email", "reply_to", "from"]) {
    const v = parseEmailAddr(String(sj[k] || ""));
    if (v && v.includes("@") && !isSelfEmail(v) && !isKamiooyaOps(v)) {
      return v;
    }
  }
  return "";
}

function buildTemplate(title: string): { subject: string; body: string } {
  const max = 40;
  const short =
    title.length <= max ? title : `${title.slice(0, max - 1)}…`;
  const company = (process.env.COMPANY_NAME || "").trim();
  const rep = (process.env.REPRESENTATIVE_NAME || "").trim();
  const personal = (process.env.PERSONAL_NAME || "").trim();
  const sig = personal || [company, rep].filter(Boolean).join("\n");
  const subject = `物件資料のご依頼（${short}）`;
  const body = [
    "お世話になっております。物件情報の送付をよろしくお願いします。",
    "併せて、固定資産評価額、修繕履歴(時期/内容/金額)が分かる資料も送付いただけると幸いです。",
    "差し支えなければ、以下についてもご教授ください。よろしくお願いします。",
    "・売却理由",
    "・売却希望時期",
    "・価格交渉可能でしょうか",
    "",
    sig,
  ].join("\n");
  return { subject, body };
}

/** queued → running の CAS（Mac worker と同じ排他） */
async function claimJobSafe(
  client: SupabaseClient,
  jobId: string,
): Promise<boolean> {
  const started = new Date().toISOString();
  const { data, error } = await client
    .from("kurashift_jobs")
    .update({
      status: "running",
      started_at: started,
      error_text: null,
    })
    .eq("id", jobId)
    .eq("status", "queued")
    .select("id")
    .maybeSingle();
  if (error) return false;
  return Boolean(data?.id);
}

export type FailoverResult = {
  ok: boolean;
  processed: number;
  results: Array<Record<string, unknown>>;
};

export async function runInquirySendFailover(opts?: {
  staleMs?: number;
  limit?: number;
}): Promise<FailoverResult> {
  if ((process.env.INQUIRY_VERCEL_FAILOVER || "1").trim() === "0") {
    return { ok: true, processed: 0, results: [{ skipped: "disabled" }] };
  }
  const client = sb();
  if (!client) {
    return {
      ok: false,
      processed: 0,
      results: [{ error: "supabase_env_missing" }],
    };
  }
  const staleMs = opts?.staleMs ?? STALE_MS;
  const limit = opts?.limit ?? 5;
  const cutoff = new Date(Date.now() - staleMs).toISOString();

  const { data: jobs, error } = await client
    .from("kurashift_jobs")
    .select("id, payload, created_at, status, title")
    .eq("job_type", "re_deal_inquiry_send")
    .eq("status", "queued")
    .lt("created_at", cutoff)
    .order("created_at", { ascending: true })
    .limit(limit);

  if (error) {
    return { ok: false, processed: 0, results: [{ error: error.message }] };
  }

  const results: Array<Record<string, unknown>> = [];
  for (const job of jobs || []) {
    const jobId = String(job.id);
    const claimed = await claimJobSafe(client, jobId);
    if (!claimed) {
      results.push({ job_id: jobId, skipped: "claim_lost" });
      continue;
    }
    const payload =
      job.payload && typeof job.payload === "object"
        ? (job.payload as Record<string, unknown>)
        : {};
    const dealId = String(payload.deal_id || "").trim();
    if (!dealId) {
      await client
        .from("kurashift_jobs")
        .update({
          status: "failed",
          error_text: "failover: deal_id missing",
          finished_at: new Date().toISOString(),
        })
        .eq("id", jobId);
      results.push({ job_id: jobId, ok: false, error: "deal_id missing" });
      continue;
    }

    const { data: deal } = await client
      .from("kurashift_re_deals")
      .select("id, title, inquiry_status, summary_json, status")
      .eq("id", dealId)
      .maybeSingle();

    if (!deal) {
      await client
        .from("kurashift_jobs")
        .update({
          status: "failed",
          error_text: "failover: deal not found",
          finished_at: new Date().toISOString(),
        })
        .eq("id", jobId);
      results.push({ job_id: jobId, ok: false, error: "deal_not_found" });
      continue;
    }

    const inq = String(deal.inquiry_status || "");
    if (["awaiting_reply", "has_reply", "sending"].includes(inq)) {
      // Mac が途中の可能性。running にしたので戻すか done skip
      await client
        .from("kurashift_jobs")
        .update({
          status: "succeeded",
          error_text: null,
          finished_at: new Date().toISOString(),
          result_json: { skipped: "inquiry_already_active", via: "vercel" },
        })
        .eq("id", jobId);
      results.push({
        job_id: jobId,
        ok: true,
        skipped: "inquiry_already_active",
      });
      continue;
    }

    const sj =
      deal.summary_json && typeof deal.summary_json === "object"
        ? (deal.summary_json as Record<string, unknown>)
        : {};
    let to = String(payload.to || "").trim() || resolveTo(sj);
    const tmpl = buildTemplate(String(deal.title || "物件"));
    const subject = String(payload.subject || tmpl.subject).trim();
    const body = String(payload.body || tmpl.body).trim();

    // 311-lite
    if (!to || !to.includes("@")) {
      await client
        .from("kurashift_jobs")
        .update({
          status: "failed",
          error_text: "failover: to unresolved (need Mac or contact_email)",
          finished_at: new Date().toISOString(),
        })
        .eq("id", jobId);
      results.push({ job_id: jobId, ok: false, error: "to_unresolved" });
      continue;
    }
    if (isSelfEmail(to) || isKamiooyaOps(to)) {
      await client
        .from("kurashift_jobs")
        .update({
          status: "failed",
          error_text: `failover: gate_311_lite blocked to=${to}`,
          finished_at: new Date().toISOString(),
        })
        .eq("id", jobId);
      results.push({ job_id: jobId, ok: false, error: "gate_blocked", to });
      continue;
    }

    try {
      const sent = await sendGmailViaEnv({
        to,
        subject,
        body,
        account: "estate",
      });
      const now = new Date().toISOString();
      const nextSj = {
        ...sj,
        inquiry_status: "awaiting_reply",
        inquiry_sent_at: now,
        inquiry_thread_id: sent.threadId || null,
        inquiry_failover: "vercel",
      };
      await client
        .from("kurashift_re_deals")
        .update({
          inquiry_status: "awaiting_reply",
          summary_json: nextSj,
          updated_at: now,
        })
        .eq("id", dealId);
      await client
        .from("kurashift_jobs")
        .update({
          status: "succeeded",
          finished_at: now,
          result_json: {
            via: "vercel_failover",
            gmail_id: sent.id,
            thread_id: sent.threadId,
            to,
          },
        })
        .eq("id", jobId);
      results.push({
        job_id: jobId,
        ok: true,
        via: "vercel_failover",
        to,
        gmail_id: sent.id,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      await client
        .from("kurashift_jobs")
        .update({
          status: "failed",
          error_text: `failover send: ${msg.slice(0, 400)}`,
          finished_at: new Date().toISOString(),
        })
        .eq("id", jobId);
      results.push({ job_id: jobId, ok: false, error: msg.slice(0, 200) });
    }
  }

  return {
    ok: results.every((r) => r.ok !== false || r.skipped),
    processed: results.length,
    results,
  };
}
