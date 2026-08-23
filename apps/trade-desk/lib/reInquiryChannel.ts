/**
 * 第一問合せの経路仕分け（メール本線 / Grok 依頼 / 対象外）
 * Python: scripts/jarvis_kurashift_re_inquiry_channel.py と同期
 */

import fs from "fs";
import path from "path";

export type InquiryChannel = "agent_email" | "grok_handoff" | "not_applicable";

export type InquiryChannelResult = {
  channel: InquiryChannel;
  /** agent_email の仲介宛、または grok_handoff の自分宛 */
  to: string;
  reason: string;
};

/** 既知の自己アドレス（クライアントでも判定するため。秘密ではない） */
const KNOWN_SELF_EMAILS = [
  "matsuno.estate@gmail.com",
  "admin@livingsupport-matsu.co.jp",
  "m19m.hrts83@gmail.com",
];

const PORTAL_DOMAIN_HINTS = [
  "kenbiya.com",
  "athome.co.jp",
  "homes.co.jp",
  "suumo.jp",
  "rakumachi.jp",
  "reins.jp",
  "reins.or.jp",
  "c21.co.jp",
  "apamanshop.com",
  "minimo.jp",
];

const NOT_APPLICABLE_TITLE_SUBSTR = [
  "業者開拓",
  "E2E-GROK-KURASHIFT",
  "approved A'",
  "approved A’",
];

export const GROK_HANDOFF_SUBJECT_PREFIX = "[KURASHIFT問合せ依頼]";

export function parseEmailAddr(raw: string | null | undefined): string {
  if (!raw) return "";
  const m = String(raw).match(/<([^>]+)>/);
  return (m ? m[1] : String(raw)).trim().toLowerCase();
}

export function selfEmailsExtraFromEnv(): string[] {
  const out: string[] = [];
  for (const k of ["PERSONAL_EMAIL", "INQUIRY_GROK_HANDOFF_TO"]) {
    const v = (process.env[k] || "").trim();
    if (v) out.push(v.toLowerCase());
  }
  return out;
}

export function isSelfEmail(
  email: string,
  extra?: string[] | null
): boolean {
  const addr = parseEmailAddr(email) || String(email || "").trim().toLowerCase();
  if (!addr || !addr.includes("@")) return false;
  if (addr.endsWith("@livingsupport-matsu.co.jp")) return true;
  if (KNOWN_SELF_EMAILS.includes(addr)) return true;
  for (const e of extra || []) {
    if (e && addr === e.trim().toLowerCase()) return true;
  }
  return false;
}

export function isPortalOrNoreplyEmail(email: string): boolean {
  const addr = parseEmailAddr(email) || String(email || "").trim().toLowerCase();
  if (!addr.includes("@")) return false;
  const local = addr.split("@")[0] || "";
  const domain = addr.split("@")[1] || "";
  if (
    local.startsWith("noreply") ||
    local.startsWith("no-reply") ||
    local === "mailer-daemon" ||
    local.startsWith("info+")
  ) {
    return true;
  }
  return PORTAL_DOMAIN_HINTS.some(
    (d) => domain === d || domain.endsWith(`.${d}`)
  );
}

export function handoffToFromEnv(): string {
  return (
    (process.env.INQUIRY_GROK_HANDOFF_TO || "").trim() ||
    (process.env.PERSONAL_EMAIL || "").trim() ||
    "m19m.hrts83@gmail.com"
  );
}

let vendorEmailCache: Map<string, string> | null = null;

function loadVendorContactEmails(): Map<string, string> {
  if (vendorEmailCache) return vendorEmailCache;
  const map = new Map<string, string>();
  const candidates = [
    path.join(process.cwd(), "..", "..", "config", "kurashift_re_vendor_list.yaml"),
    path.join(process.cwd(), "config", "kurashift_re_vendor_list.yaml"),
  ];
  for (const p of candidates) {
    try {
      if (!fs.existsSync(p)) continue;
      const raw = fs.readFileSync(p, "utf8");
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { parse } = require("yaml") as typeof import("yaml");
      const doc = parse(raw) as { vendors?: Array<{ id?: string; contact_email?: string }> };
      for (const v of doc?.vendors || []) {
        const id = String(v.id || "").trim();
        const em = String(v.contact_email || "").trim();
        if (id && em.includes("@")) map.set(id, em);
      }
      break;
    } catch {
      /* try next */
    }
  }
  vendorEmailCache = map;
  return map;
}

export function vendorContactEmail(vendorId: string | null | undefined): string {
  if (!vendorId) return "";
  return loadVendorContactEmails().get(String(vendorId).trim()) || "";
}

function sjOf(
  summaryJson: Record<string, unknown> | null | undefined
): Record<string, unknown> {
  return summaryJson && typeof summaryJson === "object" ? summaryJson : {};
}

/** 仲介宛 To を解決（自己・ポータルはスキップして次へ） */
export function resolveAgentToEmail(params: {
  summaryJson?: Record<string, unknown> | null;
  explicitTo?: string | null;
  extraSelf?: string[] | null;
}): { to: string; source: string } {
  const extra = params.extraSelf ?? selfEmailsExtraFromEnv();
  const sj = sjOf(params.summaryJson);

  const explicit = String(params.explicitTo || "").trim();
  if (explicit.includes("@") && !isSelfEmail(explicit, extra)) {
    if (!isPortalOrNoreplyEmail(explicit)) {
      return { to: parseEmailAddr(explicit) || explicit, source: "explicit" };
    }
  }

  const replyTo = parseEmailAddr(
    typeof sj.reply_to === "string" ? sj.reply_to : undefined
  );
  if (replyTo && !isSelfEmail(replyTo, extra) && !isPortalOrNoreplyEmail(replyTo)) {
    return { to: replyTo, source: "reply_to" };
  }

  const from = parseEmailAddr(typeof sj.from === "string" ? sj.from : undefined);
  if (from && !isSelfEmail(from, extra) && !isPortalOrNoreplyEmail(from)) {
    return { to: from, source: "from" };
  }

  const vendorId =
    typeof sj.vendor_id === "string"
      ? sj.vendor_id
      : sj.vendor_id != null
        ? String(sj.vendor_id)
        : "";
  const vEmail = vendorContactEmail(vendorId);
  if (vEmail && !isSelfEmail(vEmail, extra) && !isPortalOrNoreplyEmail(vEmail)) {
    return { to: parseEmailAddr(vEmail) || vEmail, source: "vendor_list" };
  }

  return { to: "", source: "none" };
}

export function isNotApplicableDeal(params: {
  title?: string | null;
  source?: string | null;
  summaryJson?: Record<string, unknown> | null;
}): boolean {
  const title = String(params.title || "");
  for (const s of NOT_APPLICABLE_TITLE_SUBSTR) {
    if (title.includes(s)) return true;
  }
  const source = String(params.source || "").trim();
  if (source === "mail_grok") return true;
  const sj = sjOf(params.summaryJson);
  const account = typeof sj.account === "string" ? sj.account : "";
  if (account === "mail_grok" && source !== "mail_admin" && source !== "mail_estate") {
    return true;
  }
  return false;
}

export function classifyInquiryChannel(params: {
  title?: string | null;
  source?: string | null;
  summaryJson?: Record<string, unknown> | null;
  explicitTo?: string | null;
  handoffTo?: string | null;
  extraSelf?: string[] | null;
}): InquiryChannelResult {
  if (
    isNotApplicableDeal({
      title: params.title,
      source: params.source,
      summaryJson: params.summaryJson,
    })
  ) {
    return {
      channel: "not_applicable",
      to: "",
      reason: "grok_report_or_vendor_outreach_memo",
    };
  }

  const agent = resolveAgentToEmail({
    summaryJson: params.summaryJson,
    explicitTo: params.explicitTo,
    extraSelf: params.extraSelf,
  });
  if (agent.to) {
    return {
      channel: "agent_email",
      to: agent.to,
      reason: `to_from_${agent.source}`,
    };
  }

  const handoff = String(params.handoffTo || handoffToFromEnv()).trim();
  return {
    channel: "grok_handoff",
    to: handoff,
    reason: "no_agent_email",
  };
}

export function buildGrokHandoffSubject(title: string, maxLen = 40): string {
  const t = title || "物件";
  const short = t.length <= maxLen ? t : `${t.slice(0, maxLen - 1)}…`;
  return `${GROK_HANDOFF_SUBJECT_PREFIX} ${short}`;
}

export function buildGrokHandoffBody(params: {
  dealId: string;
  title: string;
  inquirySubject: string;
  inquiryBody: string;
  summaryJson?: Record<string, unknown> | null;
  area?: string | null;
  priceMan?: number | null;
}): string {
  const sj = sjOf(params.summaryJson);
  const grok =
    sj.grok && typeof sj.grok === "object"
      ? (sj.grok as Record<string, unknown>)
      : null;
  const location =
    (grok && typeof grok.location === "string" ? grok.location : "") ||
    params.area ||
    params.title;
  const price =
    (grok && typeof grok.price_man_raw === "string"
      ? grok.price_man_raw
      : null) ||
    (params.priceMan != null ? String(params.priceMan) : "") ||
    (grok && grok.price_man != null ? String(grok.price_man) : "");
  const url =
    (typeof sj.url === "string" && sj.url) ||
    (typeof sj.listing_url === "string" && sj.listing_url) ||
    (grok && typeof grok.url === "string" && grok.url) ||
    "";

  return [
    "KURASHIFT からの物件第一問合せ依頼です。",
    "仲介メールが取れないため、Webフォーム問合せまたは調査フローで対応してください。",
    "",
    `deal_id: ${params.dealId}`,
    `案件: ${params.title}`,
    `住所: ${location}`,
    price ? `価格: ${price}万` : "価格: （不明）",
    url ? `URL: ${url}` : "URL: （なし）",
    "",
    "--- 希望する第一問合せ文面（参考） ---",
    `件名: ${params.inquirySubject}`,
    "",
    params.inquiryBody,
    "",
    "---",
    "完了後は従来どおり [Grok調査] または業者からの紹介メールが estate に届く想定です。",
    "※ 業者開拓 A'（地場リストの顧客登録）とは別レーンです。",
  ].join("\n");
}

export const INQUIRY_CHANNEL_LABEL: Record<InquiryChannel, string> = {
  agent_email: "メールで問合せ",
  grok_handoff: "Grokに依頼",
  not_applicable: "問合せ対象外",
};
