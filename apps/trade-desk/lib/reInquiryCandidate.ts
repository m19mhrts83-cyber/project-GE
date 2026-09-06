import {
  loadInquiryAutoConfig,
  type InquiryAutoConfig,
} from "./reInquiryAutoConfig";
import {
  classifyInquiryChannel,
  type InquiryChannel,
} from "./reInquiryChannel";

export type ReDealForInquiry = {
  id?: string;
  status?: string | null;
  source?: string | null;
  match_score?: number | null;
  title?: string | null;
  area?: string | null;
  inquiry_status?: string | null;
  summary_json?: Record<string, unknown> | null;
};

export type InquiryCandidateEval = {
  tier: 0 | 1 | 2 | 3 | null;
  tier1: boolean;
  tier2: boolean;
  tier3: boolean;
  canQuickSend: boolean;
  hasTo: boolean;
  inquiryChannel: InquiryChannel;
  revive: boolean;
  badges: string[];
  reasons: string[];
};

function sjOf(deal: ReDealForInquiry): Record<string, unknown> {
  const sj = deal.summary_json;
  return sj && typeof sj === "object" ? sj : {};
}

function grokOf(deal: ReDealForInquiry): Record<string, unknown> | null {
  const g = sjOf(deal).grok;
  return g && typeof g === "object" ? (g as Record<string, unknown>) : null;
}

export function parseEmailFromDeal(deal: ReDealForInquiry): string {
  const ch = classifyInquiryChannel({
    title: deal.title,
    source: deal.source,
    summaryJson: sjOf(deal),
  });
  if (ch.channel === "agent_email" || ch.channel === "grok_handoff") {
    return ch.to;
  }
  return "";
}

function channelOf(deal: ReDealForInquiry): ReturnType<typeof classifyInquiryChannel> {
  return classifyInquiryChannel({
    title: deal.title,
    source: deal.source,
    summaryJson: sjOf(deal),
  });
}

function inquiryStatus(deal: ReDealForInquiry): string {
  const raw =
    deal.inquiry_status ||
    (typeof sjOf(deal).inquiry_status === "string"
      ? (sjOf(deal).inquiry_status as string)
      : "none");
  return raw || "none";
}

function scoreOf(deal: ReDealForInquiry): number {
  const s = deal.match_score;
  return typeof s === "number" && !Number.isNaN(s) ? s : 0;
}

function listenValue(deal: ReDealForInquiry): string {
  const g = grokOf(deal);
  return g && typeof g.listen_value === "string" ? g.listen_value : "";
}

function hazardEval(deal: ReDealForInquiry): string {
  const g = grokOf(deal);
  return g && typeof g.hazard_eval === "string" ? g.hazard_eval : "";
}

function land100(deal: ReDealForInquiry): string {
  const g = grokOf(deal);
  return g && typeof g.land100 === "string" ? g.land100 : "";
}

function autoPassReason(deal: ReDealForInquiry): string {
  const r = sjOf(deal).auto_pass_reason;
  return typeof r === "string" ? r : "";
}

/** 神大家紹介の受付終了メール */
const UKETSUKE_SHURYO_MARKERS = ["※受付終了※", "＊受付終了＊", "*受付終了*"];

export const DEFAULT_INSTANT_DEATH_KEYWORDS = [
  "再建築不可",
  "再建築できない",
  "借地権",
  "旧法借地",
  "地上権",
  "持分売却",
  "共有持分",
  "※受付終了※",
  "＊受付終了＊",
  "*受付終了*",
  "商談中",
];

export function findInstantDeathKeyword(
  deal: ReDealForInquiry,
  cfg?: InquiryAutoConfig
): string | null {
  const kws =
    cfg?.tier3_auto_send?.instant_death_keywords || DEFAULT_INSTANT_DEATH_KEYWORDS;
  const sj = sjOf(deal);
  const blob = [
    deal.title || "",
    deal.area || "",
    typeof sj.snippet === "string" ? sj.snippet : "",
    typeof sj.body === "string" ? sj.body : "",
    typeof sj.memo === "string" ? sj.memo : "",
    typeof sj.raw_text === "string" ? sj.raw_text : "",
  ].join(" ");

  for (const kw of kws) {
    if (kw && blob.includes(kw)) {
      return kw;
    }
  }
  return null;
}

export function titleHasUketsukeShuryo(title: string | null | undefined): boolean {
  const t = String(title || "");
  return UKETSUKE_SHURYO_MARKERS.some((m) => t.includes(m));
}

function grokOverrideListen(deal: ReDealForInquiry, cfg: InquiryAutoConfig): boolean {
  const listen = listenValue(deal);
  const vals = cfg.inquiry_candidate_overrides?.grok_listen_values || [
    "聞く",
    "保留",
  ];
  return Boolean(listen && vals.includes(listen));
}

function blockedByAutoPass(deal: ReDealForInquiry, cfg: InquiryAutoConfig): boolean {
  const reason = autoPassReason(deal);
  if (!reason) return false;
  const excluded =
    cfg.inquiry_candidate_overrides?.exclude_auto_pass_reasons || [];
  if (!excluded.includes(reason)) return false;
  return !grokOverrideListen(deal, cfg);
}

function scoreMeetsTier1(deal: ReDealForInquiry, cfg: InquiryAutoConfig): boolean {
  const min = cfg.tiers?.tier1_candidate?.min_score ?? 2.0;
  return scoreOf(deal) >= min;
}

function listenMeetsTier1(deal: ReDealForInquiry, cfg: InquiryAutoConfig): boolean {
  const listen = listenValue(deal);
  const vals = cfg.tiers?.tier1_candidate?.grok_listen_values || ["聞く", "保留"];
  return Boolean(listen && vals.includes(listen));
}

function statusAllowsTier1(
  deal: ReDealForInquiry,
  cfg: InquiryAutoConfig,
  revive: boolean
): boolean {
  const st = deal.status || "";
  if (st === "info" || st === "viewing") return true;
  if (revive && st === "passed" && cfg.inquiry_candidate_overrides?.revive_passed_status) {
    return true;
  }
  return false;
}

export function evaluateInquiryCandidate(
  deal: ReDealForInquiry,
  config?: InquiryAutoConfig
): InquiryCandidateEval {
  const cfg = config || loadInquiryAutoConfig();
  const reasons: string[] = [];
  const badges: string[] = [];
  const inq = inquiryStatus(deal);
  const ch = channelOf(deal);
  const hasTo = Boolean(ch.to && ch.to.includes("@"));
  const tier0 = cfg.tiers?.tier0_exclude_inquiry_status || [
    "sending",
    "awaiting_reply",
    "awaiting_grok",
    "has_reply",
  ];

  const baseChannel = {
    inquiryChannel: ch.channel,
    hasTo,
  };

  if (tier0.includes(inq)) {
    return {
      tier: 0,
      tier1: false,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      revive: false,
      badges,
      reasons: [`inquiry_status=${inq}`],
      ...baseChannel,
    };
  }

  const allowedInq =
    cfg.tiers?.tier1_candidate?.require_inquiry_status || ["none", "draft", ""];
  if (!allowedInq.includes(inq)) {
    return {
      tier: null,
      tier1: false,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      revive: false,
      badges,
      reasons: [`inquiry_not_ready=${inq}`],
      ...baseChannel,
    };
  }

  if (ch.channel === "not_applicable") {
    return {
      tier: null,
      tier1: false,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      revive: false,
      badges: [...badges, "問合せ対象外"],
      reasons: [`channel=${ch.reason}`],
      ...baseChannel,
    };
  }

  if (ch.channel === "kamiooya_form") {
    badges.push("紹介フォーム");
    return {
      tier: 1,
      tier1: true,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      revive: false,
      badges,
      reasons: ["kamiooya_intro_form"],
      ...baseChannel,
    };
  }

  if (ch.channel === "listing_web") {
    badges.push("掲載Web問合せ");
    return {
      tier: 1,
      tier1: true,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      revive: false,
      badges,
      reasons: ["listing_web_form"],
      ...baseChannel,
    };
  }

  const deadKw = findInstantDeathKeyword(deal, cfg);
  if (deadKw) {
    return {
      tier: null,
      tier1: false,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      revive: false,
      badges: [...badges, "即死KW除外"],
      reasons: [`instant_death=${deadKw}`],
      ...baseChannel,
    };
  }

  if (titleHasUketsukeShuryo(deal.title)) {
    return {
      tier: null,
      tier1: false,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      revive: false,
      badges: [...badges, "受付終了"],
      reasons: ["uketsuke_shuryo"],
      ...baseChannel,
    };
  }

  const revive =
    deal.status === "passed" &&
    Boolean(cfg.inquiry_candidate_overrides?.revive_passed_status) &&
    grokOverrideListen(deal, cfg);

  if (revive) badges.push("再検討");

  if (blockedByAutoPass(deal, cfg)) {
    return {
      tier: null,
      tier1: false,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      revive: false,
      badges,
      reasons: [`auto_pass=${autoPassReason(deal)}`],
      ...baseChannel,
    };
  }

  if (!statusAllowsTier1(deal, cfg, revive)) {
    return {
      tier: null,
      tier1: false,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      revive,
      badges,
      reasons: [`status=${deal.status}`],
      ...baseChannel,
    };
  }

  const scoreOk = scoreMeetsTier1(deal, cfg);
  const listenOk = listenMeetsTier1(deal, cfg);
  if (!scoreOk && !listenOk) {
    return {
      tier: null,
      tier1: false,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      revive,
      badges,
      reasons: ["score/listen below tier1"],
      ...baseChannel,
    };
  }

  if (scoreOk) reasons.push(`score≥${cfg.tiers?.tier1_candidate?.min_score ?? 2}`);
  if (listenOk) reasons.push(`listen=${listenValue(deal)}`);

  const t2cfg = cfg.tiers?.tier2_daily_queue;
  const tier2 =
    listenValue(deal) === (t2cfg?.grok_listen || "聞く") &&
    scoreOf(deal) >= (t2cfg?.min_score ?? 5) &&
    hazardEval(deal) !== (t2cfg?.hazard_eval_not || "除外");

  const t3cfg = cfg.tiers?.tier3_auto_send;
  const tier3Enabled = cfg.tier3_auto_send?.enabled === true;
  const t3Min = t3cfg?.min_score ?? 7;

  // ルートA: Grok承認ルート
  const grokRoute = t3cfg?.grok_route;
  const grokMin = grokRoute?.min_score ?? t3Min;
  const routeAEligible =
    listenValue(deal) === (grokRoute?.grok_listen || t3cfg?.grok_listen || "聞く") &&
    scoreOf(deal) >= grokMin &&
    hazardEval(deal) === (grokRoute?.hazard_eval || t3cfg?.hazard_eval || "OK") &&
    land100(deal) !== (grokRoute?.land100_not || t3cfg?.land100_not || "見送り");

  // ルートB: Gmail新着高スコアルート
  const gmailRoute = t3cfg?.gmail_route;
  const gmailMin = gmailRoute?.min_score ?? t3Min;
  const allowedCh = gmailRoute?.allowed_channels || ["agent_email", "grok_handoff"];
  const routeBEligible =
    scoreOf(deal) >= gmailMin &&
    allowedCh.includes(ch.channel) &&
    hasTo;

  const tier3Eligible = routeAEligible || routeBEligible;
  const tier3 = tier3Enabled && tier3Eligible;

  if (ch.channel === "grok_handoff") badges.push("Grok依頼");
  else if (ch.channel === "agent_email") badges.push("メール問合せ");
  if (routeAEligible) reasons.push("tier3_route=grok");
  if (routeBEligible) reasons.push("tier3_route=gmail");
  if (tier2) badges.push("送信待ち");
  if (tier3) badges.push("自動可");
  else if (tier3Eligible) badges.push("Tier3候補");

  // 告知事項・心理的瑕疵・市街化調整区域の検出（除外せず価格交渉・指値材料としてバッジ化）
  const sj = sjOf(deal);
  const titleAndSnippet = [
    deal.title || "",
    deal.area || "",
    typeof sj.snippet === "string" ? sj.snippet : "",
    typeof sj.body === "string" ? sj.body : "",
  ].join(" ");
  if (titleAndSnippet.includes("告知事項") || titleAndSnippet.includes("心理的瑕疵")) {
    badges.push("告知事項あり");
    reasons.push("notice=has_kokuchi_jiko");
  }
  if (titleAndSnippet.includes("市街化調整区域") || titleAndSnippet.includes("調整区域")) {
    badges.push("市街化調整");
    reasons.push("notice=chosei_kuiki");
  }

  const tier: 1 | 2 | 3 = tier3 ? 3 : tier2 ? 2 : 1;

  return {
    tier,
    tier1: true,
    tier2,
    tier3,
    canQuickSend: true,
    revive,
    badges,
    reasons,
    ...baseChannel,
  };
}

export function dealVendorKey(deal: ReDealForInquiry): string {
  const ch = channelOf(deal);
  const toAddr = (ch.to || "").trim().toLowerCase();
  if (toAddr.includes("@")) {
    const domain = toAddr.split("@")[1]?.trim();
    if (
      domain &&
      [
        "gmail.com",
        "yahoo.co.jp",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
      ].includes(domain)
    ) {
      return `email:${toAddr}`;
    }
    if (domain) return `domain:${domain}`;
  }
  const sj = sjOf(deal);
  if (typeof sj.vendor_id === "string" && sj.vendor_id) {
    return `vendor:${sj.vendor_id}`;
  }
  return `deal:${deal.id || ""}`;
}

