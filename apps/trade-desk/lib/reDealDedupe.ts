/**
 * 千三つファネル案件の表示用重複排除・優先ソート。
 * DB は触らず、一覧／Tier2 キュー上で同一物件を畳む。
 */
import {
  classifyInquiryChannel,
  type InquiryChannel,
} from "./reInquiryChannel";

export type DealDedupeFields = {
  id: string;
  title?: string | null;
  area?: string | null;
  price_man?: number | null;
  match_score?: number | null;
  updated_at?: string | null;
  status?: string | null;
  source?: string | null;
  inquiry_status?: string | null;
  summary_json?: Record<string, unknown> | null;
};

function sjOf(deal: DealDedupeFields): Record<string, unknown> {
  const sj = deal.summary_json;
  return sj && typeof sj === "object" ? sj : {};
}

function grokOf(deal: DealDedupeFields): Record<string, unknown> | null {
  const g = sjOf(deal).grok;
  return g && typeof g === "object" ? (g as Record<string, unknown>) : null;
}

/** listing / Grok URL を抽出 */
export function dealListingUrl(deal: DealDedupeFields): string {
  const sj = sjOf(deal);
  const grok = grokOf(deal);
  for (const v of [sj.listing_url, sj.url, grok?.url]) {
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return "";
}

/** Google リダイレクト等をほどき、ホスト+パスで比較できる形に */
export function normalizeListingUrl(raw: string): string {
  let s = String(raw || "").trim();
  if (!s) return "";
  try {
    const u = new URL(s);
    if (
      (u.hostname === "www.google.com" || u.hostname === "google.com") &&
      u.pathname === "/url"
    ) {
      const q = u.searchParams.get("q") || u.searchParams.get("url");
      if (q) s = q;
    }
  } catch {
    /* keep raw */
  }
  try {
    const u = new URL(s);
    const drop = new Set([
      "utm_source",
      "utm_medium",
      "utm_campaign",
      "utm_content",
      "utm_term",
      "fbclid",
      "gclid",
    ]);
    for (const k of [...u.searchParams.keys()]) {
      if (drop.has(k) || k.startsWith("utm_")) u.searchParams.delete(k);
    }
    u.hash = "";
    let path = u.pathname.replace(/\/+$/, "") || "/";
    const qs = u.searchParams.toString();
    return `${u.hostname.toLowerCase()}${path}${qs ? `?${qs}` : ""}`;
  } catch {
    return s.toLowerCase().replace(/\/+$/, "");
  }
}

function normalizeTitle(title: string): string {
  return String(title || "")
    .normalize("NFKC")
    .replace(/^\s*(re|fw|fwd)\s*:\s*/gi, "")
    .replace(/※受付終了※/g, "")
    .replace(/＊受付終了＊/g, "")
    .replace(/\*受付終了\*/g, "")
    .replace(/\[Grok調査\]\s*/gi, "")
    .replace(/\[Grok部長\]\s*/gi, "")
    .replace(/\[KURASHIFT問合せ依頼\]\s*/gi, "")
    .replace(/[\s　]+/g, "")
    .toLowerCase();
}

function normalizeArea(area: string): string {
  return String(area || "")
    .normalize("NFKC")
    .replace(/[\s　]+/g, "")
    .toLowerCase();
}

function priceKey(price: number | null | undefined): string {
  if (typeof price !== "number" || Number.isNaN(price)) return "";
  return String(Math.round(price));
}

/**
 * 同一物件キー。
 * 1) 正規化 URL があればそれを優先
 * 2) なければ 正規化タイトル + 価格 + エリア
 */
export function dealFingerprint(deal: DealDedupeFields): string {
  const urlKey = normalizeListingUrl(dealListingUrl(deal));
  if (urlKey) return `url:${urlKey}`;

  const grok = grokOf(deal);
  const loc =
    (grok && typeof grok.location === "string" && grok.location) ||
    deal.area ||
    "";
  const t = normalizeTitle(String(deal.title || ""));
  const p = priceKey(deal.price_man);
  const a = normalizeArea(loc);
  if (t) return `tp:${t}|${p}|${a}`;
  return `id:${deal.id}`;
}

export function inquiryChannelOf(deal: DealDedupeFields): InquiryChannel {
  return classifyInquiryChannel({
    title: deal.title,
    source: deal.source,
    summaryJson: sjOf(deal),
  }).channel;
}

/** 小さいほど一覧の上（メール → 神大家フォーム → Grok Web → 対象外） */
export function channelSortRank(channel: InquiryChannel): number {
  if (channel === "agent_email") return 0;
  if (channel === "kamiooya_form") return 1;
  if (channel === "listing_web") return 2;
  if (channel === "grok_handoff") return 3;
  return 4;
}

function inquiryProgressRank(deal: DealDedupeFields): number {
  const sj = sjOf(deal);
  const raw =
    deal.inquiry_status ||
    (typeof sj.inquiry_status === "string" ? sj.inquiry_status : "none") ||
    "none";
  switch (raw) {
    case "has_reply":
      return 50;
    case "awaiting_reply":
      return 40;
    case "sent":
      return 30;
    case "sending":
      return 20;
    case "draft":
      return 10;
    default:
      return 0;
  }
}

function scoreOf(deal: DealDedupeFields): number {
  const s = deal.match_score;
  return typeof s === "number" && !Number.isNaN(s) ? s : 0;
}

function updatedMs(deal: DealDedupeFields): number {
  const t = deal.updated_at ? Date.parse(deal.updated_at) : 0;
  return Number.isNaN(t) ? 0 : t;
}

/** 同一 fingerprint 内で残す側（大きいほど勝ち） */
export function dealKeepScore(
  deal: DealDedupeFields,
  preferId?: string
): number {
  let score = 0;
  if (preferId && deal.id === preferId) score += 1_000_000;
  // メールで問合せできる案件を優先して残す
  const ch = inquiryChannelOf(deal);
  score += (2 - channelSortRank(ch)) * 10_000;
  score += inquiryProgressRank(deal) * 100;
  score += scoreOf(deal);
  score += Math.min(updatedMs(deal) / 1e12, 1); // ごく弱いタイブレーク
  return score;
}

export type DedupeResult<T extends DealDedupeFields> = {
  deals: T[];
  hiddenCount: number;
  /** fingerprint → 除外した id 一覧（デバッグ／UI注記用） */
  hiddenByFingerprint: Record<string, string[]>;
};

/** 同一案件を1件に畳む。並びはチャネル優先 → match_score → updated_at */
export function dedupeAndPrioritizeDeals<T extends DealDedupeFields>(
  deals: T[],
  opts?: { preferId?: string }
): DedupeResult<T> {
  const preferId = (opts?.preferId || "").trim();
  const best = new Map<string, T>();
  const hiddenByFingerprint: Record<string, string[]> = {};

  for (const d of deals) {
    const fp = dealFingerprint(d);
    const cur = best.get(fp);
    if (!cur) {
      best.set(fp, d);
      continue;
    }
    const keepNew =
      dealKeepScore(d, preferId) > dealKeepScore(cur, preferId);
    const winner = keepNew ? d : cur;
    const loser = keepNew ? cur : d;
    best.set(fp, winner);
    const list = hiddenByFingerprint[fp] || [];
    list.push(loser.id);
    hiddenByFingerprint[fp] = list;
  }

  const unique = [...best.values()];
  unique.sort((a, b) => {
    const ca = channelSortRank(inquiryChannelOf(a));
    const cb = channelSortRank(inquiryChannelOf(b));
    if (ca !== cb) return ca - cb;
    const sa = scoreOf(a);
    const sb = scoreOf(b);
    if (sa !== sb) return sb - sa;
    return updatedMs(b) - updatedMs(a);
  });

  const hiddenCount = deals.length - unique.length;
  return { deals: unique, hiddenCount, hiddenByFingerprint };
}
