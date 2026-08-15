/**
 * ユーザーにホームで見せる失敗ジョブ種別（変更追従: ここに足す）。
 * toast ではなく persistent banner 用。
 */
export const USER_VISIBLE_FAIL_JOB_TYPES = ["re_deal_inquiry_send"] as const;

export type UserVisibleFailJobType =
  (typeof USER_VISIBLE_FAIL_JOB_TYPES)[number];

export const FAIL_JOB_LABEL: Record<string, string> = {
  re_deal_inquiry_send: "第一問い合わせの送信",
};

export const SENDING_STALE_MINUTES = 10;

export type FailBannerItem = {
  jobId: string;
  dealId: string;
  dealTitle: string;
  errorText: string | null;
  jobType: string;
};

export type SendingStuckItem = {
  dealId: string;
  dealTitle: string;
  updatedAt: string | null;
};

type JobRow = {
  id: string;
  job_type: string;
  status: string;
  error_text?: string | null;
  created_at?: string | null;
  payload?: unknown;
  result?: unknown;
};

function asObj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
}

/** 同一 deal の最新ジョブだけを見て、failed かつ未 ack を列挙 */
export function pickUnackedFailedInquiryJobs(
  jobs: JobRow[],
  dealTitleById: Map<string, string>
): FailBannerItem[] {
  const allow = new Set<string>(USER_VISIBLE_FAIL_JOB_TYPES);
  const latestByDeal = new Map<string, JobRow>();

  for (const j of jobs) {
    if (!allow.has(j.job_type)) continue;
    const p = asObj(j.payload);
    const r = asObj(j.result);
    const dealId =
      (typeof p.deal_id === "string" && p.deal_id) ||
      (typeof r.deal_id === "string" && r.deal_id) ||
      "";
    if (!dealId) continue;
    if (!latestByDeal.has(dealId)) {
      latestByDeal.set(dealId, j);
    }
  }

  const out: FailBannerItem[] = [];
  for (const [dealId, j] of latestByDeal) {
    if (j.status !== "failed") continue;
    const r = asObj(j.result);
    if (typeof r.user_acked_at === "string" && r.user_acked_at) continue;
    out.push({
      jobId: j.id,
      dealId,
      dealTitle: dealTitleById.get(dealId) || dealId.slice(0, 8),
      errorText: j.error_text || null,
      jobType: j.job_type,
    });
  }
  return out;
}

export function pickSendingStuckDeals(
  deals: Array<{
    id: string;
    title?: string | null;
    inquiry_status?: string | null;
    updated_at?: string | null;
    summary_json?: unknown;
  }>,
  staleMinutes = SENDING_STALE_MINUTES
): SendingStuckItem[] {
  const now = Date.now();
  const staleMs = staleMinutes * 60 * 1000;
  const out: SendingStuckItem[] = [];
  for (const d of deals) {
    const sj = asObj(d.summary_json);
    const status =
      d.inquiry_status ||
      (typeof sj.inquiry_status === "string" ? sj.inquiry_status : "") ||
      "";
    if (status !== "sending") continue;
    const ts = d.updated_at ? Date.parse(d.updated_at) : NaN;
    if (!Number.isFinite(ts) || now - ts < staleMs) continue;
    out.push({
      dealId: d.id,
      dealTitle: d.title || d.id.slice(0, 8),
      updatedAt: d.updated_at || null,
    });
  }
  return out;
}
