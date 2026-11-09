/**
 * 週次レビュー（/review）の集計。メール・Slack の判断ログ（owner_decisions）を束ねる。
 *
 * ループウェアの考え方: AI が案を出す → 松野さんが判断する → 判断を残す → 週1回まとめて
 * AI の見立て（ルール候補）を松野さんが確かめる → 採用したものだけルール帳に入る。
 * このファイルは数えるだけ（DB にもネットにも触らない）。読み込みは app/review/page.tsx。
 *
 * ルール候補そのものは土曜の scripts/jarvis_loopware_weekly.py --publish が
 * sync_meta.loopware_rule_candidates に置く（ループウェアの /rules と同じ置き場）。
 */
import { editRatio, outcomeOf } from "@/lib/decisionContract";

/** メール・Slack まわりの判断（まずはここから） */
export const MAIL_SURFACES = ["triage", "triage_miss", "triage_rule", "mail_send"] as const;

export type DecisionLite = {
  id: number | string;
  decided_at: string;
  surface: string;
  action: string;
  source?: string | null;
  employee?: string | null;
  lane?: string | null;
  partner?: string | null;
  subject?: string | null;
  ai_proposal?: string | null;
  final_text?: string | null;
  edited?: boolean | null;
  note?: string | null;
  payload?: Record<string, unknown> | null;
};

export type RuleCandidate = {
  id: string;
  kind: string;
  employee: string;
  key: string;
  rule_line: string;
  text: string;
  why: string;
  evidence: (number | string)[];
  status: "hypothesis" | "candidate" | string;
  needs_ai?: boolean;
  /** どう効かせるかの選択肢（先頭が既定）。古い候補には無いので candidateOptions() で補う */
  options?: CandidateOption[];
};

export type CandidateOption = { id: string; label: string; rule_line: string; text: string };

/** 候補の選択肢。週次分析が出していなければ、候補そのものを1つの選択肢にする */
export function candidateOptions(c: RuleCandidate): CandidateOption[] {
  const opts = (Array.isArray(c.options) ? c.options : []).filter(
    (o) => o && typeof o.id === "string" && /^[a-z_]{1,20}$/.test(o.id) && typeof o.text === "string",
  );
  if (opts.length) return opts.map((o) => ({ ...o, label: o.label || "このとおり", rule_line: String(o.rule_line || "") }));
  return [{ id: "main", label: "このとおり", rule_line: c.rule_line, text: c.text }];
}

export const EMPLOYEE_LABEL: Record<string, string> = {
  "111": "111 パートナー連絡整理",
  "112": "112 LINE同期監視",
  "116": "116 メール要対応",
  "211": "211 返信案内下書き",
  vendor: "業者返信（211/115）",
};

const MISS_LABEL = "見落とし";

function pl(r: DecisionLite): Record<string, unknown> {
  return r.payload && typeof r.payload === "object" ? r.payload : {};
}

export function outcome(r: DecisionLite): string {
  const o = pl(r).outcome;
  return typeof o === "string" && o ? o : outcomeOf(String(r.action || ""));
}

export function employeeOf(r: DecisionLite): string {
  if (r.employee) return String(r.employee);
  if (r.surface === "mail_send") return "211";
  if ("slack_vr_action" in pl(r)) return "vendor";
  const lane = String(r.lane || "");
  return { partner: "111", general: "116", openchat: "112" }[lane] || "116";
}

export function isMiss(r: DecisionLite): boolean {
  return r.surface === "triage_miss" && r.action === "wrong";
}

/** 下書きからの直しの割合。記録時に入れた payload.edit_ratio を優先（無ければ計算） */
export function ratioOf(r: DecisionLite): number | null {
  const v = Number(pl(r).edit_ratio);
  if (pl(r).edit_ratio !== undefined && pl(r).edit_ratio !== null && Number.isFinite(v)) return v;
  return editRatio(r.ai_proposal, r.final_text);
}

/** 直して送ったか（edited 列が無い古い行は下書きと本文の差で見る） */
export function wasEdited(r: DecisionLite): boolean {
  if (r.action !== "sent") return false;
  if (typeof r.edited === "boolean") return r.edited;
  const e = ratioOf(r);
  return e !== null && e > 0.05;
}

export type Stats = {
  total: number;
  take: number;
  ng: number;
  hesitate: number;
  none: number;
  later: number;
  sent: number;
  edited: number;
  misses: number;
};

export function emptyStats(): Stats {
  return { total: 0, take: 0, ng: 0, hesitate: 0, none: 0, later: 0, sent: 0, edited: 0, misses: 0 };
}

export function stats(rows: DecisionLite[]): Stats {
  const s = emptyStats();
  for (const r of rows) {
    s.total += 1;
    const o = outcome(r);
    if (o === "take") s.take += 1;
    else if (o === "ng") s.ng += 1;
    else if (o === "hesitate") s.hesitate += 1;
    else if (o === "none") s.none += 1;
    else if (o === "later") s.later += 1;
    if (r.action === "sent" && r.ai_proposal) {
      s.sent += 1;
      if (wasEdited(r)) s.edited += 1;
    }
    if (isMiss(r)) s.misses += 1;
  }
  return s;
}

export type EmployeeRow = { employee: string; label: string; now: Stats; prev: Stats };

/** 社員ごとの今週と前週。今週の件数が多い順 */
export function byEmployee(now: DecisionLite[], prev: DecisionLite[]): EmployeeRow[] {
  const keys = new Set<string>([...now.map(employeeOf), ...prev.map(employeeOf)]);
  const out: EmployeeRow[] = [];
  for (const k of keys) {
    out.push({
      employee: k,
      label: EMPLOYEE_LABEL[k] || k,
      now: stats(now.filter((r) => employeeOf(r) === k)),
      prev: stats(prev.filter((r) => employeeOf(r) === k)),
    });
  }
  return out.sort((a, b) => b.now.total - a.now.total || b.prev.total - a.prev.total);
}

export function rate(n: number, d: number): number | null {
  return d > 0 ? n / d : null;
}

export function pct(v: number | null): string {
  return v === null ? "—" : `${Math.round(v * 100)}%`;
}

/** 前週比の一言（+3 / -2 / ±0） */
export function delta(now: number, prev: number): string {
  const d = now - prev;
  return d > 0 ? `+${d}` : d < 0 ? `${d}` : "±0";
}

/** 見送り・迷ったの理由タグの多い順 */
export function reasonCounts(rows: DecisionLite[], limit = 6): { tag: string; n: number }[] {
  const c = new Map<string, number>();
  for (const r of rows) {
    const o = outcome(r);
    if (o !== "ng" && o !== "hesitate") continue;
    const tags = pl(r).reason_tags;
    if (!Array.isArray(tags)) continue;
    for (const t of tags) c.set(String(t), (c.get(String(t)) || 0) + 1);
  }
  return [...c.entries()]
    .map(([tag, n]) => ({ tag, n }))
    .sort((a, b) => b.n - a.n || a.tag.localeCompare(b.tag))
    .slice(0, limit);
}

export type Trouble = {
  id: string;
  at: string;
  kind: string;
  employee: string;
  subject: string;
  detail: string;
};

/**
 * 見ておきたい判断（トラブル候補）: 見落とし・大きく直して送った・送った後の「いまいち」・どれも違う。
 * 新しい順に最大 limit 件。
 */
export function troubles(rows: DecisionLite[], limit = 10): Trouble[] {
  const out: Trouble[] = [];
  for (const r of rows) {
    const subject = String(r.subject || r.partner || r.id);
    const note = r.note ? `（${String(r.note).slice(0, 80)}）` : "";
    if (isMiss(r)) {
      out.push({ id: String(r.id), at: r.decided_at, kind: MISS_LABEL, employee: employeeOf(r), subject, detail: `出てこなかったが要対応だった${note}` });
      continue;
    }
    if (r.action === "sent" && wasEdited(r)) {
      const e = ratioOf(r);
      if (e !== null && e >= 0.3) {
        out.push({ id: String(r.id), at: r.decided_at, kind: "大きく直した", employee: employeeOf(r), subject, detail: `下書きの ${Math.round(e * 100)}% を書き換えて送った${note}` });
      }
      continue;
    }
    if (r.action === "meh" || r.action === "none_fit") {
      out.push({
        id: String(r.id),
        at: r.decided_at,
        kind: r.action === "meh" ? "いまいち" : "どれも違う",
        employee: employeeOf(r),
        subject,
        detail: (r.action === "meh" ? "送った後に「いまいち」" : "出した案がどれも違った") + note,
      });
    }
  }
  return out.sort((a, b) => b.at.localeCompare(a.at)).slice(0, limit);
}

/** sync_meta.loopware_rule_candidates の値を読む（壊れていたら空） */
export function parseCandidates(value: unknown): { week: string | null; at: string | null; candidates: RuleCandidate[] } {
  try {
    const v = (typeof value === "string" ? JSON.parse(value || "{}") : value || {}) as {
      week?: string;
      at?: string;
      candidates?: RuleCandidate[];
    };
    const cands = Array.isArray(v.candidates) ? v.candidates.filter((c) => c && /^C[0-9a-f]{8}$/.test(String(c.id))) : [];
    return { week: v.week || null, at: v.at || null, candidates: cands };
  } catch {
    return { week: null, at: null, candidates: [] };
  }
}

export type CandidateState = { decided: string | null; option: string | null; comments: string[] };

/** ルール候補ごとの、これまでの判断（採用／今回だけ／違う）とひとこと */
export function candidateStates(reviews: DecisionLite[]): Map<string, CandidateState> {
  const m = new Map<string, CandidateState>();
  const sorted = [...reviews].sort((a, b) => a.decided_at.localeCompare(b.decided_at));
  for (const r of sorted) {
    const id = String(pl(r).candidate_id || "");
    if (!id) continue;
    const s = m.get(id) || { decided: null, option: null, comments: [] };
    if (["rule_accept", "rule_once", "rule_reject"].includes(r.action)) {
      s.decided = r.action;
      s.option = r.action === "rule_accept" && pl(r).option_label ? String(pl(r).option_label) : null;
    }
    if (r.note) s.comments.push(String(r.note));
    m.set(id, s);
  }
  return m;
}

/** 分析が古い（前回から8日以上）＝土曜の週次分析が止まっているかもしれない */
export function isStale(at: string | null, now: Date = new Date()): boolean {
  if (!at) return true;
  const t = Date.parse(at);
  return !Number.isFinite(t) || now.getTime() - t > 8 * 86400_000;
}

/** ルール番号ごとの効き（payload.applied_rules） */
export function ruleEffects(rows: DecisionLite[]): { rule: string; take: number; ng: number; other: number }[] {
  const m = new Map<string, { take: number; ng: number; other: number }>();
  for (const r of rows) {
    const rules = pl(r).applied_rules;
    if (!Array.isArray(rules)) continue;
    const o = outcome(r);
    for (const id of rules) {
      const e = m.get(String(id)) || { take: 0, ng: 0, other: 0 };
      if (o === "take") e.take += 1;
      else if (o === "ng") e.ng += 1;
      else e.other += 1;
      m.set(String(id), e);
    }
  }
  return [...m.entries()].map(([rule, e]) => ({ rule, ...e })).sort((a, b) => a.rule.localeCompare(b.rule));
}

export const VERDICT_ACTION = {
  accept: "rule_accept",
  once: "rule_once",
  reject: "rule_reject",
  comment: "comment",
} as const;
export type Verdict = keyof typeof VERDICT_ACTION;
