import {
  loadInquiryAutoConfig,
  type InquiryAutoConfig,
} from "./reInquiryAutoConfig";

export type ReDealForInquiry = {
  id?: string;
  status?: string | null;
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
  const fromRaw = sjOf(deal).from;
  if (typeof fromRaw !== "string" || !fromRaw.trim()) return "";
  const m = fromRaw.match(/<([^>]+)>/);
  return (m ? m[1] : fromRaw).trim();
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
  const tier0 = cfg.tiers?.tier0_exclude_inquiry_status || [
    "sending",
    "awaiting_reply",
    "has_reply",
  ];

  if (tier0.includes(inq)) {
    return {
      tier: 0,
      tier1: false,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      hasTo: parseEmailFromDeal(deal).includes("@"),
      revive: false,
      badges,
      reasons: [`inquiry_status=${inq}`],
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
      hasTo: parseEmailFromDeal(deal).includes("@"),
      revive: false,
      badges,
      reasons: [`inquiry_not_ready=${inq}`],
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
      hasTo: parseEmailFromDeal(deal).includes("@"),
      revive: false,
      badges,
      reasons: [`auto_pass=${autoPassReason(deal)}`],
    };
  }

  if (!statusAllowsTier1(deal, cfg, revive)) {
    return {
      tier: null,
      tier1: false,
      tier2: false,
      tier3: false,
      canQuickSend: false,
      hasTo: parseEmailFromDeal(deal).includes("@"),
      revive,
      badges,
      reasons: [`status=${deal.status}`],
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
      hasTo: parseEmailFromDeal(deal).includes("@"),
      revive,
      badges,
      reasons: ["score/listen below tier1"],
    };
  }

  if (scoreOk) reasons.push(`score≥${cfg.tiers?.tier1_candidate?.min_score ?? 2}`);
  if (listenOk) reasons.push(`listen=${listenValue(deal)}`);

  const hasTo = parseEmailFromDeal(deal).includes("@");

  const t2cfg = cfg.tiers?.tier2_daily_queue;
  const tier2 =
    listenValue(deal) === (t2cfg?.grok_listen || "聞く") &&
    scoreOf(deal) >= (t2cfg?.min_score ?? 5) &&
    hazardEval(deal) !== (t2cfg?.hazard_eval_not || "除外");

  const t3cfg = cfg.tiers?.tier3_auto_send;
  const tier3Enabled = cfg.tier3_auto_send?.enabled === true;
  const tier3 =
    tier3Enabled &&
    listenValue(deal) === (t3cfg?.grok_listen || "聞く") &&
    scoreOf(deal) >= (t3cfg?.min_score ?? 7) &&
    hazardEval(deal) === (t3cfg?.hazard_eval || "OK") &&
    land100(deal) !== (t3cfg?.land100_not || "見送り");

  if (tier2) badges.push("送信待ち");
  if (tier3) badges.push("自動可");

  const tier: 1 | 2 | 3 = tier3 ? 3 : tier2 ? 2 : 1;

  return {
    tier,
    tier1: true,
    tier2,
    tier3,
    canQuickSend: true,
    hasTo,
    revive,
    badges,
    reasons,
  };
}
