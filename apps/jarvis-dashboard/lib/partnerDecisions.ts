/**
 * パートナー別の判断ログ（見送り・Todoist・後回し）。2026-11-27 松野さん了承（116・大佐 件127）。
 * 判断ログ（owner_decisions）を読んで数えるだけ。DB にもネットにも触らない（読み込みは app/mail/partners/page.tsx）。
 * 理由は本人が押した理由タグだけ。無ければ「理由なし」と出す（AI で補わない）。
 * 過去分（partner_key が無い行）は partner 名で束ねる。埋め直しはしない。
 */
import { maReasonLabel } from "@/lib/maDecisionBlocks";

export type PartnerDecisionRow = {
  id: number | string;
  decided_at: string;
  action: string;
  partner?: string | null;
  subject?: string | null;
  payload?: Record<string, unknown> | null;
};

/** 一覧に出す判断。送った（sent）は 5.やり取り.md 側に残るので対象外 */
export const PARTNER_ACTIONS = ["skipped", "hesitated", "todoist", "snoozed"] as const;
export type PartnerAction = (typeof PARTNER_ACTIONS)[number];

export const PARTNER_ACTION_LABEL: Record<PartnerAction, string> = {
  skipped: "見送り",
  hesitated: "迷って見送り",
  todoist: "Todoist",
  snoozed: "後で",
};

function pl(r: PartnerDecisionRow): Record<string, unknown> {
  return r.payload && typeof r.payload === "object" ? r.payload : {};
}

/** 束ねる鍵: 送り手の識別子（payload.partner_key）→ 無ければ partner 名 */
export function partnerKeyOf(r: PartnerDecisionRow): string {
  const k = String(pl(r).partner_key || "").trim().toLowerCase();
  if (k) return k;
  return String(r.partner || "").trim().toLowerCase();
}

/** 理由タグ（見送り・後回しのどちらも）。押していなければ空 */
export function reasonTagsOf(r: PartnerDecisionRow): string[] {
  const p = pl(r);
  const raw = p.reason_tags;
  return Array.isArray(raw) ? raw.map((t) => String(t)).filter(Boolean) : [];
}

export function reasonLabelsOf(r: PartnerDecisionRow): string[] {
  return reasonTagsOf(r).map(maReasonLabel);
}

export function isPartnerAction(a: string): a is PartnerAction {
  return (PARTNER_ACTIONS as readonly string[]).includes(a);
}

/** 対象の判断だけ（メール要対応のもの。業者返信 516 は除く） */
export function partnerRows(rows: PartnerDecisionRow[]): PartnerDecisionRow[] {
  return rows.filter((r) => isPartnerAction(r.action) && !pl(r).slack_vr_action && partnerKeyOf(r));
}

export type PartnerSummary = {
  key: string;
  name: string;
  total: number;
  counts: Record<PartnerAction, number>;
  withReason: number;
  lastAt: string;
};

export function summarizeByPartner(rows: PartnerDecisionRow[]): PartnerSummary[] {
  const map = new Map<string, PartnerSummary>();
  for (const r of partnerRows(rows)) {
    const key = partnerKeyOf(r);
    let s = map.get(key);
    if (!s) {
      s = {
        key,
        name: String(r.partner || key),
        total: 0,
        counts: { skipped: 0, hesitated: 0, todoist: 0, snoozed: 0 },
        withReason: 0,
        lastAt: r.decided_at,
      };
      map.set(key, s);
    }
    s.total += 1;
    s.counts[r.action as PartnerAction] += 1;
    if (reasonTagsOf(r).length) s.withReason += 1;
    if (r.decided_at > s.lastAt) {
      s.lastAt = r.decided_at;
      s.name = String(r.partner || s.name);
    }
  }
  return [...map.values()].sort((a, b) => b.total - a.total || (a.lastAt < b.lastAt ? 1 : -1));
}

/** 1パートナーの判断（新しい順） */
export function decisionsForPartner(rows: PartnerDecisionRow[], key: string): PartnerDecisionRow[] {
  const k = key.trim().toLowerCase();
  return partnerRows(rows)
    .filter((r) => partnerKeyOf(r) === k)
    .sort((a, b) => (a.decided_at < b.decided_at ? 1 : -1));
}
