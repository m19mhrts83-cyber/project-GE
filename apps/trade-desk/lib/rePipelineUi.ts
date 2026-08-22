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

export function grokOneLine(grok: Record<string, unknown> | null): string {
  if (!grok) return "—";
  const parts: string[] = [];
  if (typeof grok.listen_value === "string" && grok.listen_value) {
    parts.push(`聞く:${grok.listen_value}`);
  }
  if (typeof grok.hazard_eval === "string" && grok.hazard_eval) {
    parts.push(`HZ:${grok.hazard_eval}`);
  }
  if (typeof grok.land100 === "string" && grok.land100) {
    parts.push(`土地:${grok.land100}`);
  }
  if (typeof grok.population_eval === "string" && grok.population_eval) {
    parts.push(`人口:${grok.population_eval}`);
  }
  return parts.length ? parts.join(" · ") : "—";
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
