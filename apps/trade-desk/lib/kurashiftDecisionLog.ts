/**
 * KURASHIFT の判断ログ（/decisions）を組み立てる純粋な部品。
 * 材料はアプリの表だけ（kurashift_money_ops.assist_payload.decision_log・kurashift_re_deal_events）。
 * owner_decisions（共有の判断ログ）は DB トリガーが写すので、ここでは読まない。
 */
import { MONEY_STATUS_LABEL, tagLabel } from "./kurashiftDecision";

export type DecisionKind = "money" | "deal";
export type Outcome = "take" | "ng" | "hesitate" | "later" | "note";

export type DecisionRow = {
  key: string;
  kind: DecisionKind;
  at: string;
  targetId: string;
  title: string;
  /** 例: 「承認」「見送り」 */
  label: string;
  outcome: Outcome;
  amountJpy: number | null;
  reasonTags: string[];
  reasonLabels: string[];
  note: string | null;
  always: boolean;
  by: string | null;
};

type MoneyOp = {
  id: string;
  title: string | null;
  amount_jpy?: number | string | null;
  assist_payload?: unknown;
};

type DealEvent = {
  id: string;
  deal_id: string;
  event_type: string;
  actor?: string | null;
  occurred_at: string;
  payload?: unknown;
};

const MONEY_OUTCOME: Record<string, Outcome> = {
  approved: "take",
  done: "take",
  cancelled: "ng",
  consulting: "hesitate",
};

const DEAL_LABEL: Record<string, { label: string; outcome: Outcome }> = {
  confirm: { label: "候補に残す（問合せへ）", outcome: "take" },
  pass: { label: "見送り", outcome: "ng" },
  pursue_add: { label: "進行中に入れる", outcome: "take" },
  pursue_remove: { label: "進行中から外す", outcome: "later" },
  set_viewing: { label: "内見へ", outcome: "take" },
  set_offer: { label: "買付へ", outcome: "take" },
};

function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

function tags(v: unknown): string[] {
  return Array.isArray(v) ? v.map((t) => String(t)).filter(Boolean) : [];
}

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function moneyRows(ops: MoneyOp[]): DecisionRow[] {
  const out: DecisionRow[] = [];
  for (const op of ops) {
    const log = obj(op.assist_payload).decision_log;
    if (!Array.isArray(log)) continue;
    log.forEach((raw, i) => {
      const e = obj(raw);
      const to = String(e.to || "");
      const outcome = MONEY_OUTCOME[to];
      if (!outcome) return; // 実行中へ・草案に戻すは判断ではない
      const t = tags(e.reason_tags);
      out.push({
        key: `m:${op.id}:${i}`,
        kind: "money",
        at: String(e.at || ""),
        targetId: op.id,
        title: op.title || "（無題の資金移動）",
        label: MONEY_STATUS_LABEL[to] || to,
        outcome,
        amountJpy: num(e.amount_jpy) ?? num(op.amount_jpy),
        reasonTags: t,
        reasonLabels: t.map(tagLabel),
        note: typeof e.note === "string" && e.note ? e.note : null,
        always: e.scope === "always",
        by: typeof e.by === "string" ? e.by : null,
      });
    });
  }
  return out;
}

export function dealRows(
  events: DealEvent[],
  titles: Map<string, string>
): DecisionRow[] {
  const out: DecisionRow[] = [];
  for (const ev of events) {
    if ((ev.actor || "") !== "user") continue;
    const p = obj(ev.payload);
    const meta = DEAL_LABEL[String(p.action || "")];
    if (!meta) continue;
    const t = tags(p.reason_tags);
    out.push({
      key: `d:${ev.id}`,
      kind: "deal",
      at: ev.occurred_at,
      targetId: ev.deal_id,
      title: titles.get(ev.deal_id) || "（物件）",
      label: meta.label,
      outcome: meta.outcome,
      amountJpy: null,
      reasonTags: t,
      reasonLabels: t.map(tagLabel),
      note: typeof p.note === "string" && p.note ? p.note : null,
      always: p.scope === "always",
      by: typeof p.decided_by === "string" ? p.decided_by : null,
    });
  }
  return out;
}

export type DecisionSummary = {
  total: number;
  take: number;
  ng: number;
  hesitate: number;
  later: number;
  /** 理由（タグかひとこと）が付いた割合 0〜1。0件なら null */
  reasonRate: number | null;
  /** 2件以上同じ理由（共通パターン）。1件だけのものは一般化しない */
  patterns: { tag: string; label: string; count: number; kind: DecisionKind; outcome: Outcome }[];
  /** 「次も同じに」が付いた判断（基準の候補） */
  ruleCandidates: DecisionRow[];
};

export function summarize(rows: DecisionRow[]): DecisionSummary {
  const s: DecisionSummary = {
    total: rows.length,
    take: 0,
    ng: 0,
    hesitate: 0,
    later: 0,
    reasonRate: null,
    patterns: [],
    ruleCandidates: [],
  };
  let withReason = 0;
  const counts = new Map<string, { count: number; kind: DecisionKind; outcome: Outcome; tag: string }>();
  for (const r of rows) {
    if (r.outcome === "take") s.take++;
    else if (r.outcome === "ng") s.ng++;
    else if (r.outcome === "hesitate") s.hesitate++;
    else if (r.outcome === "later") s.later++;
    if (r.reasonTags.length || r.note) withReason++;
    if (r.always) s.ruleCandidates.push(r);
    for (const t of r.reasonTags) {
      const k = `${r.kind}:${r.outcome}:${t}`;
      const cur = counts.get(k) || { count: 0, kind: r.kind, outcome: r.outcome, tag: t };
      cur.count++;
      counts.set(k, cur);
    }
  }
  s.reasonRate = rows.length ? withReason / rows.length : null;
  s.patterns = [...counts.values()]
    .filter((c) => c.count >= 2)
    .sort((a, b) => b.count - a.count)
    .map((c) => ({ ...c, label: tagLabel(c.tag) }));
  return s;
}

export function sortNewest(rows: DecisionRow[]): DecisionRow[] {
  return [...rows].sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}
