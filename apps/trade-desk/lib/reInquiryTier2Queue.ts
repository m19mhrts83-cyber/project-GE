import type { SupabaseClient } from "@supabase/supabase-js";
import {
  evaluateInquiryCandidate,
  parseEmailFromDeal,
  type ReDealForInquiry,
} from "./reInquiryCandidate";
import { isProductionInquiryDeal } from "./reInquiryProductionFilter";
import { buildInquiryPreview } from "./reInquiryPreview";
import {
  loadInquiryAutoConfig,
  type InquiryAutoConfig,
} from "./reInquiryAutoConfig";

export type Tier2QueueItem = {
  deal_id: string;
  title: string;
  match_score: number | null;
  area: string | null;
  has_to: boolean;
  to: string;
  subject: string;
  body: string;
  body_preview: string;
  land_method_bairitsu: boolean;
  badges: string[];
};

export function isTier2Enabled(config?: InquiryAutoConfig): boolean {
  const cfg = config || loadInquiryAutoConfig();
  const t2 = cfg.tiers?.tier2_daily_queue as
    | { enabled?: boolean }
    | undefined;
  return t2?.enabled === true;
}

/** JST 当日 0:00 を ISO で返す */
export function jstDayStartIso(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const y = parts.find((p) => p.type === "year")?.value ?? "1970";
  const m = parts.find((p) => p.type === "month")?.value ?? "01";
  const d = parts.find((p) => p.type === "day")?.value ?? "01";
  return `${y}-${m}-${d}T00:00:00+09:00`;
}

export async function countTodayInquirySends(
  supabase: SupabaseClient
): Promise<number> {
  const since = jstDayStartIso();
  const { count, error } = await supabase
    .from("kurashift_jobs")
    .select("id", { count: "exact", head: true })
    .eq("job_type", "re_deal_inquiry_send")
    .in("status", ["queued", "running", "succeeded"])
    .gte("created_at", since);
  if (error) return 0;
  return count || 0;
}

export function buildTier2QueueFromDeals(
  deals: ReDealForInquiry[],
  config?: InquiryAutoConfig
): Tier2QueueItem[] {
  const cfg = config || loadInquiryAutoConfig();
  if (!isTier2Enabled(cfg)) return [];

  const items: Tier2QueueItem[] = [];
  for (const deal of deals) {
    if (!isProductionInquiryDeal(deal, cfg)) continue;
    const evalInq = evaluateInquiryCandidate(deal, cfg);
    if (!evalInq.tier2 || !evalInq.canQuickSend) continue;

    const sj =
      deal.summary_json && typeof deal.summary_json === "object"
        ? (deal.summary_json as Record<string, unknown>)
        : {};
    const fromRaw = typeof sj.from === "string" ? sj.from : null;
    const preview = buildInquiryPreview({
      title: String(deal.title || "物件"),
      summaryJson: sj,
      fromRaw,
    });
    const to = preview.to || parseEmailFromDeal(deal);
    if (!to.includes("@")) continue;

    items.push({
      deal_id: String(deal.id),
      title: String(deal.title || ""),
      match_score:
        typeof deal.match_score === "number" ? deal.match_score : null,
      area: deal.area != null ? String(deal.area) : null,
      has_to: true,
      to,
      subject: preview.subject,
      body: preview.body,
      body_preview: preview.body.slice(0, 280),
      land_method_bairitsu: preview.land_method_bairitsu,
      badges: evalInq.badges,
    });
  }

  items.sort(
    (a, b) => (b.match_score ?? 0) - (a.match_score ?? 0)
  );
  return items;
}

export async function getTier2QueueSummary(
  supabase: SupabaseClient
): Promise<{
  enabled: boolean;
  daily_cap: number;
  sent_today: number;
  remaining: number;
  queue: Tier2QueueItem[];
}> {
  const cfg = loadInquiryAutoConfig();
  const enabled = isTier2Enabled(cfg);
  const dailyCap = cfg.daily_send_cap ?? 5;
  const sentToday = await countTodayInquirySends(supabase);
  const remaining = Math.max(0, dailyCap - sentToday);

  if (!enabled) {
    return {
      enabled: false,
      daily_cap: dailyCap,
      sent_today: sentToday,
      remaining,
      queue: [],
    };
  }

  const { data: deals } = await supabase
    .from("kurashift_re_deals")
    .select(
      "id, title, status, match_score, area, inquiry_status, summary_json"
    )
    .in("status", ["info", "viewing"])
    .order("match_score", { ascending: false, nullsFirst: false })
    .limit(120);

  const fullQueue = buildTier2QueueFromDeals(
    (deals || []) as ReDealForInquiry[],
    cfg
  );
  const capped = fullQueue.slice(0, remaining);

  return {
    enabled: true,
    daily_cap: dailyCap,
    sent_today: sentToday,
    remaining,
    queue: capped,
  };
}
