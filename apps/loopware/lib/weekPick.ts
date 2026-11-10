/**
 * 今週の9件（/week）。日曜の夜に、先週残ったものを振り返り、おすすめ9件を直して月・水・金に置く。
 * 材料は scripts/jarvis_todoist_weekly_pick.py（snapshot）が sync_meta.weekly_pick_snapshot に置く。
 * 確定すると owner_decisions（surface=weekly_pick）に判断を残し、action=commit の plan を
 * 同じスクリプト（reflect・30分ごと）が Todoist に反映する。
 *
 * 外部に依存しない純粋な部品（テスト: tests/weekPick.test.ts）。
 */
import type { DecisionInput } from "./decisionContract";

export const PICK_REASONS: Record<string, string> = {
  deadline: "締切が近い",
  waiting_other: "相手を待たせている",
  partner_money: "パートナー・お金の仕事",
  carried: "先週から残っている",
  small: "小さくすぐ終わる",
  interest: "興味・勢いがある",
  inlet: "入口で待っている",
  planned: "前の週の見通しで置いていた",
};

export const LEFT_REASONS: Record<string, string> = {
  no_time: "時間が足りなかった",
  waiting: "相手待ち・材料待ち",
  too_big: "大きすぎた・気が重い",
  lower_priority: "優先が下がった",
  ai_dev: "AI開発に時間を使った",
};

export const NEXT_STEPS = {
  keep: "来週も入れる",
  split: "分ける",
  to_ai: "AIに渡す",
  drop: "やめる",
} as const;
export type NextStep = keyof typeof NEXT_STEPS;

export type Reason = { tag: string; text: string };

export type Candidate = {
  kind: "task";
  id: string;
  title: string;
  mark: "ai" | "requested" | "none";
  labels: string[];
  priority: string;
  due: string | null;
  deadline: string | null;
  hard: boolean;
  left_from_last: boolean;
  weeks_carried: number;
  score: number;
  reasons: Reason[];
  url: string;
};

export type InletCandidate = {
  kind: "inlet";
  id: string;
  title: string;
  body: string;
  source_ref: string | null;
  waited_days: number;
  score: number;
  reasons: Reason[];
};

export type Snapshot = {
  v: number;
  rule_version: string;
  generated_at: string;
  week: string;
  days: string[];
  per_day: number;
  last: { week: string; done: number; done_titles: string[]; left: number; added: number; owner_open: number };
  candidates: Candidate[];
  inlet: InletCandidate[];
  recommended: { id: string; day: string }[];
  next_preview: string[];
  dated_in_week: { id: string; title: string; date: string; hard: boolean }[];
  hard_ahead: { id: string; title: string; date: string }[];
};

export type LeftAnswer = { tags: string[]; next: NextStep; note: string };
export type PickReason = { tags: string[]; text: string };
export type InletChoice = { action: "week" | "keep" | "skip"; day?: string };

export type WeekState = {
  slots: Record<string, string | null>; // task id → 置いた日（null＝置かない）
  reasons: Record<string, PickReason>;
  left: Record<string, LeftAnswer>;
  inlet: Record<string, InletChoice>;
  keepDate: Record<string, boolean>; // この週に期日があるが選ばなかったもの: true＝期日を残す
};

export type Plan = {
  set_due: { id: string; date: string }[];
  clear_due: string[];
  notes: { id: string; text: string }[];
  inlet: { topic_id: string; title: string; date: string | null; source_ref: string | null }[];
  inlet_skip: string[];
};

const WD = ["日", "月", "火", "水", "木", "金", "土"];

/** "2026-11-16" → 曜日（0=日） */
export function weekday(iso: string): number {
  return new Date(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10))).getUTCDay();
}

/** "2026-11-16" → "11/16(月)" */
export function dayLabel(iso: string): string {
  return `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}(${WD[weekday(iso)]})`;
}

/** iso に n 日足す */
export function addDays(iso: string, n: number): string {
  const d = new Date(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10) + n));
  return d.toISOString().slice(0, 10);
}

export type CalEvent = { date: string; start: string | null; end: string | null; all_day: boolean; title: string; kind: string; end_date?: string };
export type Calendar = { generated_at: string; from: string; to: string; events: CalEvent[] };

/** カレンダーのマスに出す短い件名（先頭の [..] 【..】 を外す） */
export function shortTitle(t: string): string {
  const s = t.replace(/^(\s*(\[[^\]]*\]|【[^】]*】))+\s*/, "").trim();
  return s || t;
}

/** 3週間（割り付ける週の月曜から21日）の日付 */
export function threeWeeks(monday: string): string[][] {
  return [0, 1, 2].map((w) => Array.from({ length: 7 }, (_, i) => addDays(monday, w * 7 + i)));
}

/** 日ごとの予定（終日で複数日にまたがるものは各日に） */
export function eventsByDay(cal: Calendar | null): Record<string, CalEvent[]> {
  const out: Record<string, CalEvent[]> = {};
  for (const e of cal?.events || []) {
    const last = e.all_day && e.end_date && e.end_date > e.date ? e.end_date : e.date;
    for (let d = e.date, i = 0; d <= last && i < 31; d = addDays(d, 1), i++) (out[d] ||= []).push(e);
  }
  return out;
}

/** AI の案から最初の状態を作る（おすすめはそのまま置き、理由は最初の1つを選んだ形） */
export function initialState(s: Snapshot): WeekState {
  const slots: Record<string, string | null> = {};
  const reasons: Record<string, PickReason> = {};
  for (const r of s.recommended) slots[r.id] = r.day;
  for (const c of s.candidates) {
    const first = c.reasons[0];
    reasons[c.id] = { tags: first ? [first.tag] : [], text: first ? first.text : "" };
  }
  for (const c of s.inlet) {
    const first = c.reasons[0];
    reasons[`inlet:${c.id}`] = { tags: first ? [first.tag] : [], text: first ? first.text : "" };
  }
  const left: Record<string, LeftAnswer> = {};
  for (const c of s.candidates) if (c.left_from_last) left[c.id] = { tags: [], next: "keep", note: "" };
  return { slots, reasons, left, inlet: {}, keepDate: {} };
}

export function dayCounts(s: Snapshot, st: WeekState): Record<string, number> {
  const out: Record<string, number> = Object.fromEntries(s.days.map((d) => [d, 0]));
  for (const d of Object.values(st.slots)) if (d && d in out) out[d] += 1;
  for (const v of Object.values(st.inlet)) if (v.action === "week" && v.day && v.day in out) out[v.day] += 1;
  return out;
}

/** 確定した状態 → Todoist への反映内容 */
export function buildPlan(s: Snapshot, st: WeekState): Plan {
  const set_due: Plan["set_due"] = [];
  const picked = new Set<string>();
  for (const [id, day] of Object.entries(st.slots)) {
    if (day) {
      set_due.push({ id, date: day });
      picked.add(id);
    }
  }
  const clear = new Set<string>();
  for (const x of s.dated_in_week) {
    if (!picked.has(x.id) && !x.hard && !st.keepDate[x.id]) clear.add(x.id);
  }
  const byId = new Map(s.candidates.map((c) => [c.id, c]));
  const notes: Plan["notes"] = [];
  for (const [id, a] of Object.entries(st.left)) {
    const c = byId.get(id);
    const why = a.tags.map((t) => LEFT_REASONS[t] || t).join("・");
    const tail = [why && `残った理由: ${why}`, a.note && `ひとこと: ${a.note}`].filter(Boolean).join("／");
    if (a.next === "keep") {
      if (tail && picked.has(id)) notes.push({ id, text: `週次：来週も入れる。${tail}` });
      continue;
    }
    const head = a.next === "split" ? "週次：分けて進める（次の一手を決める）" : a.next === "to_ai" ? "週次：AIに渡す" : "週次：やめると判断（片付けは 313）";
    notes.push({ id, text: tail ? `${head}。${tail}` : head });
    if ((a.next === "to_ai" || a.next === "drop") && !picked.has(id) && c?.due && !c.hard) clear.add(id);
  }
  const inlet: Plan["inlet"] = [];
  const inlet_skip: string[] = [];
  for (const c of s.inlet) {
    const v = st.inlet[c.id];
    if (!v) continue;
    if (v.action === "skip") inlet_skip.push(c.id);
    else inlet.push({ topic_id: c.id, title: c.title, date: v.action === "week" ? v.day || null : null, source_ref: c.source_ref });
  }
  return { set_due, clear_due: [...clear], notes, inlet, inlet_skip };
}

/** 判断ログの行（owner_decisions）。nonce は確定ごとに1つ（確定し直すと新しい行になる） */
export function buildDecisions(s: Snapshot, st: WeekState, plan: Plan, nonce: string, decidedAt: string): DecisionInput[] {
  const out: DecisionInput[] = [];
  const base = { surface: "weekly_pick", source: "loopware", employee: "312", timing: { decided_at: decidedAt } };
  const key = (k: string) => `weekly:${s.week}:${nonce}:${k}`;
  const recDay = new Map(s.recommended.map((r) => [r.id, r.day]));
  const byId = new Map(s.candidates.map((c) => [c.id, c]));

  for (const [id, a] of Object.entries(st.left)) {
    const c = byId.get(id);
    out.push({
      ...base,
      action: "left",
      targetType: "todoist_task",
      targetId: id,
      subject: c?.title || null,
      reasonTags: a.tags,
      nextStep: a.next,
      note: a.note || null,
      idemKey: key(`left:${id}`),
      payload: { week: s.week, weeks_carried: c?.weeks_carried ?? 0 },
    });
  }

  const shown = new Set<string>([...recDay.keys(), ...Object.keys(st.slots).filter((id) => st.slots[id])]);
  let rank = 0;
  for (const c of s.candidates) {
    rank += 1;
    if (!shown.has(c.id)) continue;
    const day = st.slots[c.id] || null;
    const r = st.reasons[c.id] || { tags: [], text: "" };
    out.push({
      ...base,
      action: day ? "pick" : "defer",
      targetType: "todoist_task",
      targetId: c.id,
      subject: c.title,
      aiProposal: c.reasons.map((x) => x.text).join("／") || null,
      finalText: r.text || null,
      reasonTags: r.tags,
      idemKey: key(`task:${c.id}`),
      payload: {
        week: s.week,
        day,
        ai_day: recDay.get(c.id) || null,
        recommended: recDay.has(c.id),
        rank,
        score: c.score,
        hard: c.hard,
        rule_version: s.rule_version,
      },
    });
  }

  for (const c of s.inlet) {
    const v = st.inlet[c.id];
    if (!v) continue;
    const r = st.reasons[`inlet:${c.id}`] || { tags: [], text: "" };
    out.push({
      ...base,
      action: v.action === "week" ? "pick" : v.action === "keep" ? "todo" : "skipped",
      targetType: "task_loop_topic",
      targetId: c.id,
      subject: c.title,
      aiProposal: c.reasons.map((x) => x.text).join("／") || null,
      finalText: r.text || null,
      reasonTags: r.tags,
      idemKey: key(`inlet:${c.id}`),
      payload: { week: s.week, day: v.day || null, waited_days: c.waited_days },
    });
  }

  const picked = plan.set_due.length + plan.inlet.filter((x) => x.date).length;
  const fromAi = s.recommended.filter((r) => st.slots[r.id] === r.day).length;
  out.push({
    ...base,
    action: "commit",
    targetType: "weekly_plan",
    targetId: s.week,
    idemKey: key("commit"),
    payload: {
      week: s.week,
      plan,
      counts: { picked, recommended: s.recommended.length, kept_ai_slot: fromAi, left: Object.keys(st.left).length },
      last: s.last,
      rule_version: s.rule_version,
      snapshot_at: s.generated_at,
    },
  });
  return out;
}
