/** 不動産パイプライン — ラベル・フィルタ（UI 共有） */

export const DEAL_STATUS_LABEL: Record<string, string> = {
  info: "情報",
  viewing: "内見",
  offer: "買付",
  loan: "融資",
  purchased: "購入",
  passed: "見送り",
  archived: "アーカイブ",
};

export const INQUIRY_STATUS_LABEL: Record<string, string> = {
  none: "未送信",
  draft: "下書き",
  sent: "送信済",
  awaiting_reply: "返信待ち",
  awaiting_grok: "Grok依頼中",
  has_reply: "返信あり",
};

export const VENDOR_STATUS_LABEL: Record<string, string> = {
  pending: "未送信",
  discovered: "探索",
  contacted: "送信済",
  replied: "返信あり",
  skip: "スキップ",
  invalid: "無効",
};

export const ALIVE_STATUS_LABEL: Record<string, string> = {
  unknown: "未確認",
  ok: "生存OK",
  fail: "不通/失敗",
  stale: "期限切れ",
};

export type DealsTabId = "candidates" | "all" | "passed";

export function parseDealsTab(raw: string | undefined): DealsTabId {
  if (raw === "all" || raw === "passed") return raw;
  return "candidates";
}

export function vendorNeedsFollowUp(v: {
  status: string;
  contacted_at?: string | null;
}): boolean {
  if (v.status === "replied") return true;
  if (v.status !== "contacted" || !v.contacted_at) return false;
  const sent = new Date(v.contacted_at);
  if (Number.isNaN(sent.getTime())) return false;
  const days = (Date.now() - sent.getTime()) / (86400 * 1000);
  return days >= 7;
}

/** alive_ok = status ok かつ期限内（due_days） */
export function vendorAliveOk(v: {
  alive_status?: string | null;
  alive_checked_at?: string | null;
  alive_due_days?: number | null;
}): boolean {
  if ((v.alive_status || "unknown") !== "ok") return false;
  if (!v.alive_checked_at) return false;
  const checked = new Date(v.alive_checked_at);
  if (Number.isNaN(checked.getTime())) return false;
  const due = typeof v.alive_due_days === "number" && v.alive_due_days > 0
    ? v.alive_due_days
    : 180;
  const days = (Date.now() - checked.getTime()) / (86400 * 1000);
  return days < due;
}

export function vendorAliveEffective(v: {
  alive_status?: string | null;
  alive_checked_at?: string | null;
  alive_due_days?: number | null;
}): string {
  const st = v.alive_status || "unknown";
  if (st === "ok" && !vendorAliveOk(v)) return "stale";
  if ((st === "unknown" || !st) && !v.alive_checked_at) return "stale";
  return st;
}

export function grokOneLine(grok: Record<string, unknown> | null): string {
  if (!grok) return "—";
  const parts: string[] = [];
  if (typeof grok.listen_value === "string" && grok.listen_value) {
    parts.push(`聞く:${grok.listen_value}`);
  }
  if (typeof grok.hazard_eval === "string" && grok.hazard_eval) {
    parts.push(`HZ:${grok.hazard_eval}`);
  }
  const landPct = formatLandValuePct(grok);
  if (landPct !== "不明") {
    parts.push(`土地値:${landPct}`);
  } else if (typeof grok.land100 === "string" && grok.land100) {
    parts.push(`土地:${grok.land100}`);
  }
  if (typeof grok.population_eval === "string" && grok.population_eval) {
    parts.push(`人口:${grok.population_eval}`);
  }
  return parts.length ? parts.join(" · ") : "—";
}

/**
 * 土地値／購入価格の比率（Grok land100_ratio 優先）。不明は「不明」。
 */
export function formatLandValuePct(
  grok: Record<string, unknown> | null | undefined
): string {
  if (!grok) return "不明";
  const raw = grok.land100_ratio ?? grok.land_ratio;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    const n = raw <= 3 ? raw * 100 : raw; // 1.23 → 123%
    return `${Math.round(n)}%`;
  }
  if (typeof raw === "string") {
    const t = raw.trim();
    if (!t || t === "-" || t === "—" || /要確認|不明|なし|n\/?a/i.test(t)) {
      return "不明";
    }
    const m = t.match(/(\d+(?:\.\d+)?)\s*%?/);
    if (m) {
      const n = Number(m[1]);
      if (!Number.isFinite(n)) return "不明";
      const pct = n <= 3 && !t.includes("%") ? n * 100 : n;
      return `${Math.round(pct)}%`;
    }
  }
  return "不明";
}

export function lastActivityLine(
  messages: Array<{ occurred_at?: string; subject?: string; direction?: string }>,
  events: Array<{ occurred_at?: string; summary?: string; event_type?: string }>
): { at: string; text: string } {
  type Item = { at: string; text: string; ts: number };
  const items: Item[] = [];
  for (const m of messages) {
    if (!m.occurred_at) continue;
    const ts = new Date(m.occurred_at).getTime();
    const dir = m.direction === "inbound" ? "返信" : "送信";
    items.push({
      at: m.occurred_at,
      text: `${dir}: ${(m.subject || "").slice(0, 40)}`,
      ts,
    });
  }
  for (const e of events) {
    if (!e.occurred_at) continue;
    items.push({
      at: e.occurred_at,
      text: e.summary || e.event_type || "—",
      ts: new Date(e.occurred_at).getTime(),
    });
  }
  items.sort((a, b) => b.ts - a.ts);
  return items[0] || { at: "", text: "—" };
}

export const SOURCE_BADGE: Record<string, string> = {
  mail_grok: "Grok",
  mail_estate: "estate",
  mail_admin: "admin",
  kenbiya: "健美家",
  rakumachi: "楽待",
  manual: "手動",
  other: "その他",
};

function asSj(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  return {};
}

function grokOf(sj: Record<string, unknown>): Record<string, unknown> | null {
  return sj.grok && typeof sj.grok === "object" && !Array.isArray(sj.grok)
    ? (sj.grok as Record<string, unknown>)
    : null;
}

/** 取込の由来（アカウント名ではなく人が読む出所） */
export function dealOriginLabel(params: {
  title?: string | null;
  source?: string | null;
  summaryJson?: Record<string, unknown> | null;
}): string {
  const title = String(params.title || "");
  const source = String(params.source || "").trim();
  const sj = asSj(params.summaryJson);
  const grok = grokOf(sj);
  if (
    source === "mail_grok" ||
    title.includes("[Grok調査]") ||
    title.includes("Grok調査") ||
    grok
  ) {
    return "Grok調査結果";
  }
  if (
    sj.kamiooya_intro === true ||
    /【神大家】\s*物件紹介/.test(title) ||
    (typeof sj.interest_form_url === "string" && sj.interest_form_url.trim())
  ) {
    return "神大家物件紹介";
  }
  if (source === "mail_estate" || source === "mail_admin") {
    return "メール候補";
  }
  if (typeof sj.gmail_id === "string" && sj.gmail_id.trim()) {
    return "メール取込";
  }
  return SOURCE_BADGE[source] || source || "その他";
}

/** 一覧用の短い出所チップ */
export function dealOriginChip(params: {
  title?: string | null;
  source?: string | null;
  summaryJson?: Record<string, unknown> | null;
}): "Grok" | "メール" | string {
  const label = dealOriginLabel(params);
  if (label === "Grok調査結果") return "Grok";
  if (label === "神大家物件紹介") return "神大家";
  if (label.startsWith("メール")) return "メール";
  return label.slice(0, 6);
}

export function dealListingUrl(
  summaryJson?: Record<string, unknown> | null
): string | null {
  const sj = asSj(summaryJson);
  const grok = grokOf(sj);
  for (const v of [sj.listing_url, sj.url, grok?.url]) {
    if (typeof v === "string" && /^https?:\/\//i.test(v.trim())) {
      return v.trim();
    }
  }
  return null;
}

/** Gmail 箱 → authuser（複数アカウント時に #all/id だけだと一覧落ちする） */
const GMAIL_AUTHUSER: Record<string, string> = {
  mail_admin: "admin@livingsupport-matsu.co.jp",
  admin: "admin@livingsupport-matsu.co.jp",
  mail_estate: "matsuno.estate@gmail.com",
  estate: "matsuno.estate@gmail.com",
  mail_m19m: "m19m.hrts83@gmail.com",
  m19m: "m19m.hrts83@gmail.com",
};

/**
 * 特定メールを開く deep link。
 * authuser 付きでないと、ブラウザの既定 Google アカウントで id が見つからず一覧に落ちる。
 */
export function gmailDeepLink(
  gmailId: string,
  accountOrSource?: string | null
): string {
  const id = gmailId.trim();
  const key = (accountOrSource || "").trim();
  const authuser = GMAIL_AUTHUSER[key];
  if (authuser) {
    return `https://mail.google.com/mail/?authuser=${encodeURIComponent(authuser)}#all/${id}`;
  }
  return `https://mail.google.com/mail/u/0/#all/${id}`;
}

export function dealGmailUrl(
  summaryJson?: Record<string, unknown> | null,
  source?: string | null
): string | null {
  const sj = asSj(summaryJson);
  const id = typeof sj.gmail_id === "string" ? sj.gmail_id.trim() : "";
  if (!id) return null;
  const accountHint =
    (typeof sj.account === "string" && sj.account.trim()) ||
    (source && source.trim()) ||
    (typeof sj.source === "string" && sj.source.trim()) ||
    null;
  return gmailDeepLink(id, accountHint);
}

export function dealScoreReasonLine(params: {
  matchScore?: number | null;
  summaryJson?: Record<string, unknown> | null;
}): string {
  const sj = asSj(params.summaryJson);
  const grok = grokOf(sj);
  const parts: string[] = [];
  if (Array.isArray(sj.hits)) {
    const hits = (sj.hits as unknown[])
      .map((h) => String(h || "").trim())
      .filter(Boolean)
      .slice(0, 4);
    if (hits.length) parts.push(hits.join("・"));
  }
  const grokLine = grokOneLine(grok);
  if (grokLine !== "—") parts.push(grokLine);
  if (parts.length) return parts.join(" · ");
  if (params.matchScore != null && Number(params.matchScore) > 0) {
    return "根拠データなし（スコアのみ）";
  }
  return "根拠データなし";
}

export type DealNextAction = {
  code:
    | "reply"
    | "email_inquiry"
    | "grok_handoff"
    | "kamiooya_form"
    | "hz_research"
    | "triage";
  line: string;
  primaryCta: string;
};

export function dealRecommendedNext(params: {
  status?: string | null;
  title?: string | null;
  source?: string | null;
  inquiryStatus?: string | null;
  summaryJson?: Record<string, unknown> | null;
  inquiryEval?: {
    tier1?: boolean;
    inquiryChannel?: "agent_email" | "grok_handoff" | "kamiooya_form" | "not_applicable" | string;
  } | null;
}): DealNextAction {
  const sj = asSj(params.summaryJson);
  const inquiryStatus =
    params.inquiryStatus ||
    (typeof sj.inquiry_status === "string" ? sj.inquiry_status : "none");
  const channel = params.inquiryEval?.inquiryChannel;
  const tier1 = Boolean(params.inquiryEval?.tier1);
  const grok = grokOf(sj);
  const origin = dealOriginLabel({
    title: params.title,
    source: params.source,
    summaryJson: sj,
  });

  if (inquiryStatus === "has_reply") {
    return {
      code: "reply",
      line: "返信を確認 → フォーム下書き",
      primaryCta: "返信確認",
    };
  }
  if (
    channel === "kamiooya_form" ||
    sj.kamiooya_intro === true ||
    (typeof sj.interest_form_url === "string" && sj.interest_form_url.trim())
  ) {
    if (
      inquiryStatus === "awaiting_reply" ||
      inquiryStatus === "sent" ||
      inquiryStatus === "awaiting_grok"
    ) {
      return {
        code: "kamiooya_form",
        line: "紹介フォーム送信済 → 運営の物件情報返信を待つ",
        primaryCta: "運営返信待ち",
      };
    }
    return {
      code: "kamiooya_form",
      line: "紹介フォームで詳細請求（メール返信ではない）",
      primaryCta: "紹介フォームを開く",
    };
  }
  if (tier1 && channel === "agent_email") {
    return {
      code: "email_inquiry",
      line: "第一問合せ（メール）を送る",
      primaryCta: "メールで問合せ",
    };
  }
  if (tier1 && channel === "grok_handoff") {
    return {
      code: "grok_handoff",
      line: "Grok依頼（HP／Web問合せ）を送る",
      primaryCta: "Grok依頼",
    };
  }
  if (origin === "Grok調査結果") {
    const hz =
      typeof grok?.hazard_eval === "string" ? grok.hazard_eval.trim() : "";
    const thin = !grok || !hz || hz === "不明" || hz === "保留";
    if (thin) {
      return {
        code: "hz_research",
        line: "路線価・HZ 追加調査（仲介メール問合せは不要）",
        primaryCta: "路線価・HZ追加調査",
      };
    }
    return {
      code: "triage",
      line: "調査結果を見て「確認した（問合せへ）／見送り」で仕分け（次は図面・マイソク。まだ内見ではない）",
      primaryCta: "確認した／見送り",
    };
  }
  return {
    code: "triage",
    line: "「確認した（問合せへ）／見送り」で仕分け（確認した＝詳細問合せへ。内見・買い進めではない）",
    primaryCta: "確認した／見送り",
  };
}
