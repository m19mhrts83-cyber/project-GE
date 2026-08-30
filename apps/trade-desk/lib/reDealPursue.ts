/**
 * 案件ファネルの一覧ブロック判定。
 * - 進行中（詳細〜内見）: 問合せ進行 / viewing / 明示フォロー（pursue）
 * - 買い進め（買付・融資）: offer | loan | purchased のみ
 * 「確認した」(user_confirmed) だけではどちらにも入れない。
 *
 * クライアント（DealDetailDrawer 等）からも import されるため、
 * fs / YAML 読取（reInquiryAutoConfig）に依存しない。
 */
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

const BUY_PUSH = new Set(["offer", "loan", "purchased"]);
const INQUIRY_ACTIVE = new Set([
  "sent",
  "sending",
  "awaiting_reply",
  "awaiting_grok",
  "has_reply",
]);

const UKETSUKE_MARKERS = ["※受付終了※", "＊受付終了＊", "*受付終了*"];
const NOISE_TITLE = [
  "業者開拓",
  "E2E-GROK-KURASHIFT",
  "[Grok部長] 日報",
  "日報 20",
];

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

export function isPursueNoiseTitle(title: string | null | undefined): boolean {
  const t = String(title || "");
  if (UKETSUKE_MARKERS.some((m) => t.includes(m))) return true;
  return NOISE_TITLE.some((n) => t.includes(n));
}

/** クライアント安全な本番フィルタ（E2E・受付終了など） */
function isProductionOk(d: PursueDealFields): boolean {
  if (isPursueNoiseTitle(d.title)) return false;
  const sj = sjOf(d);
  const grok =
    sj.grok && typeof sj.grok === "object"
      ? (sj.grok as Record<string, unknown>)
      : null;
  const blob = [
    String(d.title || ""),
    String(sj.e2e ?? ""),
    String(sj.report_id ?? ""),
    String(grok?.e2e ?? ""),
    String(grok?.report_id ?? ""),
  ].join("\n");
  if (blob.includes("E2E-GROK-KURASHIFT")) return false;
  return true;
}

/** ユーザーが明示除外（進行中から外す） */
export function isPursueExcluded(d: PursueDealFields): boolean {
  return sjOf(d).pursue_exclude === true;
}

/** 明示フォロー印（「進行中に入れる」）。user_confirmed だけでは false */
export function isExplicitFollowFlag(d: PursueDealFields): boolean {
  const sj = sjOf(d);
  if (sj.pursue_exclude === true) return false;
  if (sj.pursue === true) return true;
  if (typeof sj.pursue_at === "string" && sj.pursue_at) return true;
  return false;
}

/**
 * @deprecated 旧「買い進め」判定。user_confirmed を含むため新規は isInProgressDeal / isBuyPushDeal を使う。
 */
export function isUserPursueFlag(d: PursueDealFields): boolean {
  const sj = sjOf(d);
  if (sj.pursue_exclude === true) return false;
  if (isExplicitFollowFlag(d)) return true;
  if (sj.user_confirmed === true) return true;
  if (typeof sj.user_confirmed_at === "string" && sj.user_confirmed_at) {
    return true;
  }
  return false;
}

function baseOk(d: PursueDealFields): boolean {
  const st = String(d.status || "");
  if (st === "passed" || st === "archived") return false;
  if (!isProductionOk(d)) return false;
  if (isPursueExcluded(d)) return false;
  return true;
}

/** フェーズ5: 買付証明〜融資・購入 */
export function isBuyPushDeal(d: PursueDealFields): boolean {
  if (!baseOk(d)) return false;
  return BUY_PUSH.has(String(d.status || ""));
}

/**
 * 進行中（詳細問合せ〜内見）。買い進め（offer以降）は含めない。
 * user_confirmed のみでは入れない。
 */
export function isInProgressDeal(d: PursueDealFields): boolean {
  if (!baseOk(d)) return false;
  const st = String(d.status || "");
  if (BUY_PUSH.has(st)) return false;

  if (st === "viewing") return true;
  if (INQUIRY_ACTIVE.has(inquiryOf(d))) return true;
  if (isExplicitFollowFlag(d) && (st === "info" || st === "viewing")) {
    return true;
  }
  return false;
}

/**
 * @deprecated 互換。買い進め＝買付以降のみに狭めた isBuyPushDeal を優先。
 */
export function isBuyProgressDeal(d: PursueDealFields): boolean {
  return isBuyPushDeal(d) || isInProgressDeal(d);
}

export function filterBuyPushDeals<T extends PursueDealFields>(deals: T[]): T[] {
  const list = deals.filter(isBuyPushDeal);
  const order = (s: string) => {
    if (s === "purchased") return 0;
    if (s === "loan") return 1;
    if (s === "offer") return 2;
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

export function filterInProgressDeals<T extends PursueDealFields>(
  deals: T[]
): T[] {
  const list = deals.filter(isInProgressDeal);
  const order = (s: string) => {
    if (s === "viewing") return 0;
    if (s === "info") return 1;
    return 9;
  };
  list.sort((a, b) => {
    const oa = order(String(a.status || ""));
    const ob = order(String(b.status || ""));
    if (oa !== ob) return oa - ob;
    const ia = INQUIRY_ACTIVE.has(inquiryOf(a)) ? 0 : 1;
    const ib = INQUIRY_ACTIVE.has(inquiryOf(b)) ? 0 : 1;
    if (ia !== ib) return ia - ib;
    return (b.match_score ?? 0) - (a.match_score ?? 0);
  });
  return list;
}

/** @deprecated filterInProgressDeals + filterBuyPushDeals を使う */
export function filterBuyProgressDeals<T extends PursueDealFields>(
  deals: T[]
): T[] {
  return [...filterBuyPushDeals(deals), ...filterInProgressDeals(deals)];
}
