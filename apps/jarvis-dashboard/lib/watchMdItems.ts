export type WatchMdItem = {
  name: string;
  title: string;
  action: string;
  priority: string;
  bodyMd: string;
};

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

function fromUnknown(v: unknown): WatchMdItem | null {
  const o = asRecord(v);
  const name = String(o.name || "").trim();
  const bodyMd = String(o.body_md || o.bodyMd || "").trim();
  if (!name && !bodyMd) return null;
  return {
    name,
    title: String(o.title || "").trim() || name,
    action: String(o.action || "").trim(),
    priority: String(o.priority || "").trim(),
    bodyMd,
  };
}

/** grok_bridge_inbox.pending / hawk_weekly_summary.items */
export function readWatchMdItems(payload: Record<string, unknown>): WatchMdItem[] {
  const keys = ["pending", "items"] as const;
  for (const key of keys) {
    const raw = payload[key];
    if (!Array.isArray(raw) || raw.length === 0) continue;
    const items = raw.map(fromUnknown).filter((x): x is WatchMdItem => Boolean(x));
    if (items.some((x) => x.bodyMd)) return items;
  }
  return [];
}

export function isMarkdownWatchId(id: string): boolean {
  return id === "grok_bridge_inbox" || id === "hawk_weekly_summary";
}
