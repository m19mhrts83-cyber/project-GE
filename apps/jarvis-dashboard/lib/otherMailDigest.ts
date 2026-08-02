/** sync_meta.other_mail_digest の JSON */

import { mailPriorityToLevel } from "@/lib/homeLevels";

export type OtherMailActionItem = {
  id?: string;
  subject?: string;
  from?: string;
  reason?: string;
};

export type OtherMailDigest = {
  generated_at?: string;
  pending_count?: number;
  overview?: string;
  action_items?: OtherMailActionItem[];
  lines?: string[];
};

/** triage_items 行から digest を組み立てるときの最小列 */
export type OtherMailRow = {
  subject: string | null;
  from_email: string | null;
  partner: string | null;
  summary: string | null;
  priority: string | null;
};

export function parseOtherMailDigest(
  raw: string | undefined | null,
): OtherMailDigest | null {
  if (!raw || !raw.trim()) return null;
  try {
    const v = JSON.parse(raw) as OtherMailDigest;
    if (!v || typeof v !== "object") return null;
    return v;
  } catch {
    return null;
  }
}

/**
 * sync_meta が無いときの簡易 digest。
 * 注: インライン `{...}[]` 引数型は一部 SWC で `Expression expected` になるため型別名を使う。
 */
export function fallbackOtherMailDigest(
  otherMails: OtherMailRow[],
): OtherMailDigest {
  const n = otherMails.length;
  if (n === 0) {
    return {
      overview: "パートナー以外の未読はありません。",
      action_items: [],
      lines: [],
      pending_count: 0,
    };
  }
  const domains = new Map<string, number>();
  for (const m of otherMails) {
    const from = m.from_email || m.partner || "不明";
    const dom = from.includes("@") ? from.split("@").pop() || from : from;
    domains.set(dom, (domains.get(dom) || 0) + 1);
  }
  const top = [...domains.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([d, c]) => `${d}×${c}`)
    .join("、");
  const action = otherMails
    .filter((m) => mailPriorityToLevel(m.priority) === "attention")
    .slice(0, 5)
    .map((m) => ({
      subject: m.subject || "（件名なし）",
      from: m.from_email || m.partner || undefined,
      reason: "優先度: 要確認（参考）",
    }));
  return {
    overview: `未読 ${n} 件。主な差出: ${top || "—"}。ざざっと見て、残したいものだけ開いてください。`,
    action_items: action,
    lines: otherMails.slice(0, 4).map((m) => {
      const who = m.from_email || m.partner || "—";
      return `${who}: ${m.subject || "（件名なし）"}`;
    }),
    pending_count: n,
  };
}
