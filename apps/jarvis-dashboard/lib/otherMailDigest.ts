/** sync_meta.other_mail_digest の JSON */

import { mailPriorityToLevel } from "@/lib/homeLevels";

export type OtherMailActionItem = {
  id?: string;
  subject?: string;
  from?: string;
  reason?: string;
};

export type OtherMailGenre = {
  id: string;
  label: string;
  item_ids: string[];
  bullets: string[];
  ask_hint?: string;
};

export type OtherMailDigest = {
  generated_at?: string;
  pending_count?: number;
  mail_count?: number;
  skim_count?: number;
  overview?: string;
  action_items?: OtherMailActionItem[];
  genres?: OtherMailGenre[];
  lines?: string[];
  via?: string;
};

/** triage_items 行から digest を組み立てるときの最小列 */
export type OtherMailRow = {
  id?: string;
  kind?: string | null;
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
 */
export function fallbackOtherMailDigest(
  otherMails: OtherMailRow[],
): OtherMailDigest {
  const n = otherMails.length;
  if (n === 0) {
    return {
      overview: "パートナー以外の未読はありません。",
      action_items: [],
      genres: [],
      lines: [],
      pending_count: 0,
      mail_count: 0,
      skim_count: 0,
    };
  }
  const mailRows = otherMails.filter((m) => (m.kind || "mail") === "mail");
  const skimRows = otherMails.filter((m) => m.kind === "skim");
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
  const action = mailRows
    .filter((m) => mailPriorityToLevel(m.priority) === "attention")
    .slice(0, 5)
    .map((m) => ({
      id: m.id,
      subject: m.subject || "（件名なし）",
      from: m.from_email || m.partner || undefined,
      reason: "優先度: 要確認（参考）",
    }));
  const genres: OtherMailGenre[] = [
    {
      id: "other",
      label: "未分類（フォールバック）",
      item_ids: otherMails.map((m) => m.id || "").filter(Boolean),
      bullets: otherMails.slice(0, 4).map((m) => {
        const who = m.from_email || m.partner || "—";
        return `${who}: ${m.subject || "（件名なし）"}`;
      }),
      ask_hint: "この一覧について詳しく聞きたい",
    },
  ];
  return {
    overview: `未読 ${n} 件（要確認 ${mailRows.length} / 要約 ${skimRows.length}）。主な差出: ${top || "—"}。`,
    action_items: action,
    genres,
    lines: genres.map((g) => `${g.label}（${g.item_ids.length}）`),
    pending_count: n,
    mail_count: mailRows.length,
    skim_count: skimRows.length,
  };
}
