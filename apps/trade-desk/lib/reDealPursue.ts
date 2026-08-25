/**
 * 「いま買い進めている」物件の判定。
 * - 買付・融資・購入
 * - 内見＋（問合せ進行 / Grok「聞く」 / ユーザー確認 pursue）
 */
import { titleHasUketsukeShuryo } from "./reInquiryCandidate";
import { isProductionInquiryDeal } from "./reInquiryProductionFilter";

export type PursueDealFields = {
  id: string;
  title?: string | null;
  status?: string | null;
  area?: string | null;
  price_man?: number | null;
  match_score?: number | null;
  inquiry_status?: string | null;
  source?: string | null;
  summary_json?: Record<string, unknown> | null;
  updated_at?: string | null;
};

const FUNNEL_ACTIVE = new Set(["offer", "loan", "purchased"]);
const INQUIRY_ACTIVE = new Set([
  "sent",
  "sending",
  "awaiting_reply",
  "awaiting_grok",
  "has_reply",
]);

function sjOf(d: PursueDealFields): Record<string, unknown> {
  const sj = d.summary_json;
  return sj && typeof sj === "object" ? sj : {};
}

function inquiryOf(d: PursueDealFields): string {
  const sj = sjOf(d);
  return (
    d.inquiry_status ||
    (typeof sj.inquiry_status === "string" ? sj.inquiry_status : "none") ||
    "none"
  );
}

function grokListen(d: PursueDealFields): string {
  const g = sjOf(d).grok;
  if (!g || typeof g !== "object") return "";
  const v = (g as Record<string, unknown>).listen_value;
  return typeof v === "string" ? v : "";
}

const NOISE_TITLE = [
  "業者開拓",
  "E2E-GROK-KURASHIFT",
  "[Grok部長] 日報",
  "日報 20",
];

export function isPursueNoiseTitle(title: string | null | undefined): boolean {
  const t = String(title || "");
  if (titleHasUketsukeShuryo(t)) return true;
  return NOISE_TITLE.some((n) => t.includes(n));
}

/** ユーザーが「確認した」または明示 pursue */
export function isUserPursueFlag(d: PursueDealFields): boolean {
  const sj = sjOf(d);
  if (sj.pursue === true || sj.user_confirmed === true) return true;
  if (typeof sj.pursue_at === "string" && sj.pursue_at) return true;
  if (typeof sj.user_confirmed_at === "string" && sj.user_confirmed_at) return true;
  return false;
}

export function isBuyProgressDeal(d: PursueDealFields): boolean {
  const st = String(d.status || "");
  if (st === "passed" || st === "archived" || st === "info") return false;
  if (isPursueNoiseTitle(d.title)) return false;
  if (!isProductionInquiryDeal(d)) return false;

  if (FUNNEL_ACTIVE.has(st)) return true;

  if (st === "viewing") {
    if (isUserPursueFlag(d)) return true;
    if (INQUIRY_ACTIVE.has(inquiryOf(d))) return true;
    if (grokListen(d) === "聞く") return true;
  }
  return false;
}

export function filterBuyProgressDeals<T extends PursueDealFields>(
  deals: T[]
): T[] {
  const list = deals.filter(isBuyProgressDeal);
  const order = (s: string) => {
    if (s === "purchased") return 0;
    if (s === "loan") return 1;
    if (s === "offer") return 2;
    if (s === "viewing") return 3;
    return 9;
  };
  list.sort((a, b) => {
    const oa = order(String(a.status || ""));
    const ob = order(String(b.status || ""));
    if (oa !== ob) return oa - ob;
    return (b.match_score ?? 0) - (a.match_score ?? 0);
  });
  return list;
}
