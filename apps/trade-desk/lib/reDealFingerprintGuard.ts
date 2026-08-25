/**
 * 同一物件 fingerprint での二重問合せ抑止（DB 列 property_fingerprint + 計算指紋）。
 * 表示用畳み込み（reDealDedupe）の次段: 別 deal_id でも送信をブロックする。
 */
import {
  dealFingerprint,
  type DealDedupeFields,
} from "./reDealDedupe";

/** 既に問合せが進んでいるとみなすステータス */
export const FINGERPRINT_BLOCK_INQUIRY_STATUSES = [
  "sent",
  "sending",
  "awaiting_reply",
  "has_reply",
  "grok_pending",
  "awaiting_grok",
] as const;

export type FingerprintBlockStatus =
  (typeof FINGERPRINT_BLOCK_INQUIRY_STATUSES)[number];

const JOB_BLOCK_STATUSES = ["queued", "running", "succeeded"] as const;

export type DealForFingerprintGuard = DealDedupeFields & {
  property_fingerprint?: string | null;
};

export type FingerprintSendGuardOk = {
  blocked: false;
  fingerprint: string;
};

export type FingerprintSendGuardBlocked = {
  blocked: true;
  fingerprint: string;
  reason: string;
  sibling_deal_id?: string;
  sibling_inquiry_status?: string;
  sibling_job_id?: string;
  sibling_job_status?: string;
};

export type FingerprintSendGuardResult =
  | FingerprintSendGuardOk
  | FingerprintSendGuardBlocked;

type SupabaseFromClient = {
  from: (table: string) => {
    select: (cols: string) => any;
  };
};

function sjOf(deal: DealForFingerprintGuard): Record<string, unknown> {
  const sj = deal.summary_json;
  return sj && typeof sj === "object" ? sj : {};
}

export function resolveDealFingerprint(deal: DealForFingerprintGuard): string {
  const stored = String(deal.property_fingerprint || "").trim();
  if (stored) return stored;
  return dealFingerprint(deal);
}

function inquiryStatusOf(deal: DealForFingerprintGuard): string {
  const sj = sjOf(deal);
  return (
    String(
      deal.inquiry_status ||
        (typeof sj.inquiry_status === "string" ? sj.inquiry_status : "none") ||
        "none"
    ) || "none"
  );
}

function isBlockStatus(status: string): boolean {
  return (FINGERPRINT_BLOCK_INQUIRY_STATUSES as readonly string[]).includes(
    status
  );
}

/** 敗者: archived + duplicate_of + fingerprint */
export function mergeLoserSummaryPatch(
  sj: Record<string, unknown> | null | undefined,
  winnerId: string,
  fingerprint: string
): Record<string, unknown> {
  const base =
    sj && typeof sj === "object" ? { ...sj } : ({} as Record<string, unknown>);
  base.duplicate_of = winnerId;
  base.property_fingerprint = fingerprint;
  base.dedupe_merged_at = new Date().toISOString();
  return base;
}

/** 勝者: fingerprint + 統合した loser id 一覧 */
export function mergeWinnerSummaryPatch(
  sj: Record<string, unknown> | null | undefined,
  loserIds: string[],
  fingerprint: string
): Record<string, unknown> {
  const base =
    sj && typeof sj === "object" ? { ...sj } : ({} as Record<string, unknown>);
  const prev = Array.isArray(base.dedupe_merged_ids)
    ? (base.dedupe_merged_ids as unknown[]).map(String)
    : [];
  const merged = [...new Set([...prev, ...loserIds.map(String)])];
  base.property_fingerprint = fingerprint;
  base.dedupe_merged_ids = merged;
  base.dedupe_merged_at = new Date().toISOString();
  delete base.duplicate_of;
  return base;
}

/**
 * 同一 fingerprint の別案件が既に送信／進行中、または送信ジョブがあるときブロック。
 */
export async function checkFingerprintSendGuard(
  supabase: SupabaseFromClient,
  deal: DealForFingerprintGuard
): Promise<FingerprintSendGuardResult> {
  const fingerprint = resolveDealFingerprint(deal);
  const selfId = String(deal.id || "");

  // 1) 列で紐づく兄弟
  const { data: byCol, error: colErr } = await supabase
    .from("kurashift_re_deals")
    .select(
      "id, title, area, price_man, match_score, updated_at, status, source, inquiry_status, summary_json, property_fingerprint"
    )
    .eq("property_fingerprint", fingerprint)
    .neq("id", selfId)
    .limit(40);

  if (colErr && !/property_fingerprint|column/i.test(String(colErr.message))) {
    return {
      blocked: true,
      fingerprint,
      reason: `fingerprint_guard_query_failed: ${colErr.message}`,
    };
  }

  const siblings: DealForFingerprintGuard[] = [
    ...((byCol || []) as DealForFingerprintGuard[]),
  ];

  // 2) 進行中ステータスの案件を計算指紋で突合（列未埋めで補完）
  const { data: inProgress } = await supabase
    .from("kurashift_re_deals")
    .select(
      "id, title, area, price_man, match_score, updated_at, status, source, inquiry_status, summary_json, property_fingerprint"
    )
    .in("inquiry_status", [...FINGERPRINT_BLOCK_INQUIRY_STATUSES])
    .neq("id", selfId)
    .limit(200);

  for (const row of (inProgress || []) as DealForFingerprintGuard[]) {
    if (siblings.some((s) => s.id === row.id)) continue;
    if (resolveDealFingerprint(row) === fingerprint) siblings.push(row);
  }

  for (const sib of siblings) {
    const st = inquiryStatusOf(sib);
    if (isBlockStatus(st)) {
      return {
        blocked: true,
        fingerprint,
        reason: "同一物件の別案件が既に問合せ進行中です",
        sibling_deal_id: String(sib.id),
        sibling_inquiry_status: st,
      };
    }
  }

  // 3) 送信ジョブ（自分以外の deal_id）
  const siblingIds = new Set(siblings.map((s) => String(s.id)));
  const { data: jobs } = await supabase
    .from("kurashift_jobs")
    .select("id, status, payload")
    .eq("job_type", "re_deal_inquiry_send")
    .in("status", [...JOB_BLOCK_STATUSES])
    .order("created_at", { ascending: false })
    .limit(80);

  const jobDealIds: string[] = [];
  const jobsByDeal = new Map<string, { id: string; status: string }>();
  for (const j of jobs || []) {
    const p =
      j.payload && typeof j.payload === "object"
        ? (j.payload as Record<string, unknown>)
        : {};
    const did = String(p.deal_id || "");
    if (!did || did === selfId) continue;
    jobDealIds.push(did);
    if (!jobsByDeal.has(did)) {
      jobsByDeal.set(did, { id: String(j.id), status: String(j.status) });
    }
  }

  // 既知兄弟のジョブ
  for (const did of siblingIds) {
    const job = jobsByDeal.get(did);
    if (job) {
      return {
        blocked: true,
        fingerprint,
        reason: "同一物件の別案件に送信ジョブがあります",
        sibling_deal_id: did,
        sibling_job_id: job.id,
        sibling_job_status: job.status,
      };
    }
  }

  // ジョブ先 deal を読み fingerprint 突合（兄弟未登録分）
  const unknownJobIds = [...new Set(jobDealIds)].filter(
    (id) => !siblingIds.has(id)
  );
  if (unknownJobIds.length > 0) {
    const { data: jobDeals } = await supabase
      .from("kurashift_re_deals")
      .select(
        "id, title, area, price_man, match_score, updated_at, status, source, inquiry_status, summary_json, property_fingerprint"
      )
      .in("id", unknownJobIds.slice(0, 40));

    for (const row of (jobDeals || []) as DealForFingerprintGuard[]) {
      if (resolveDealFingerprint(row) !== fingerprint) continue;
      const job = jobsByDeal.get(String(row.id));
      return {
        blocked: true,
        fingerprint,
        reason: "同一物件の別案件に送信ジョブがあります",
        sibling_deal_id: String(row.id),
        sibling_job_id: job?.id,
        sibling_job_status: job?.status,
      };
    }
  }

  return { blocked: false, fingerprint };
}
