/**
 * 今週の9件（/week）。日曜の夜に、先週残ったものを振り返り、おすすめ9件を直して月・水・金に置く。
 * 材料は scripts/jarvis_todoist_weekly_pick.py（snapshot）が sync_meta.weekly_pick_snapshot に置く。
 * 確定すると owner_decisions（surface=weekly_pick）に判断を残し、action=commit の plan を
 * 同じスクリプト（reflect・30分ごと）が Todoist に反映する。
 *
 * 判断の重さ（2026-11-23 松野さん）: 各件に weight（quick＝すぐ決まる／deep＝じっくり／unknown＝未判別）と
 * 根拠1行（weight_why）が付く。基準は config/todoist_weekly_weight.yaml（snapshot 側で判定。AI は呼ばない）。
 * おすすめは「じっくりは週1件・すぐ決まるは月→水→金に前倒し」で作られる。本人が置き直した下書きは上書きしない。
 * じっくりの1件は週2回の「じっくり枠」（deep_frame.days。既定は火・金）に、同じ件の1回目・2回目として置く。
 * 9件の上限は枠の回数も含めて数える。枠には社員1名のフロー磨き込みも入れられる（本人が決める。config か画面で。
 * Todoist には起票しない＝判断ログに残すだけ）。
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

export type Weight = "quick" | "deep" | "unknown";
export const WEIGHT_LABEL: Record<Weight, string> = { quick: "すぐ決まる", deep: "じっくり", unknown: "未判別" };

export type WeightInfo = {
  ok: boolean;
  error: string;
  decision_id: string;
  labels: Record<Weight, string>;
  deep_per_week: number | null;
  recommended: Record<Weight, number>;
  candidates: Record<Weight, number>;
  deferred: { id: string; reason: string }[];
};

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
  weight?: Weight; // 古い snapshot には無い（未判別として扱う）
  weight_why?: string;
};

export type DeepFrame = {
  days: string[]; // じっくり枠の日（同じ件の1回目・2回目）
  recommended: string | null; // 枠の案（じっくりのタスク）。社員が決まっている週は null
  staff_label: string;
  staff_steps: string[];
  staff: { staff: string; decision_id: string; title: string } | null; // 本人が決めた社員（config）
};

/** じっくり枠に入れるもの。本人が選ぶ（社員は自動で決めない） */
export type DeepChoice =
  | { kind: "task"; id: string }
  | { kind: "staff"; name: string; decision_id?: string }
  | { kind: "none" };

export type InletCandidate = {
  kind: "inlet";
  id: string;
  title: string;
  body: string;
  source_ref: string | null;
  waited_days: number;
  score: number;
  reasons: Reason[];
  weight?: Weight;
  weight_why?: string;
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
  weight?: WeightInfo; // rule-v2 から
  deep_frame?: DeepFrame | null;
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
  deep?: DeepChoice; // じっくり枠（古い下書きには無い → 案のまま）
};

export type Plan = {
  set_due: { id: string; date: string }[];
  clear_due: string[];
  notes: { id: string; text: string }[];
  inlet: { topic_id: string; title: string; date: string | null; source_ref: string | null }[];
  inlet_skip: string[];
  deep_frame?: { kind: "task" | "staff"; id?: string; name?: string; days: string[] } | null; // 記録用（社員は Todoist に起票しない）
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
  const st: WeekState = { slots, reasons, left, inlet: {}, keepDate: {} };
  if (s.deep_frame) st.deep = initialDeep(s);
  return st;
}

/** じっくり枠の最初の案: 本人が決めた社員（config）＞ じっくりのタスクの案 ＞ 空き */
export function initialDeep(s: Snapshot): DeepChoice {
  const f = s.deep_frame;
  if (f?.staff) return { kind: "staff", name: f.staff.staff, decision_id: f.staff.decision_id };
  if (f?.recommended) return { kind: "task", id: f.recommended };
  return { kind: "none" };
}

/** いまのじっくり枠（下書きに無ければ案のまま） */
export function deepOf(s: Snapshot, st: WeekState): DeepChoice {
  if (!s.deep_frame) return { kind: "none" };
  return st.deep || initialDeep(s);
}

/** じっくり枠に出す題 */
export function deepTitle(s: Snapshot, d: DeepChoice): string {
  if (d.kind === "task") return s.candidates.find((c) => c.id === d.id)?.title || d.id;
  if (d.kind === "staff") {
    if (s.deep_frame?.staff && s.deep_frame.staff.staff === d.name) return s.deep_frame.staff.title;
    const steps = s.deep_frame?.staff_steps?.join("→");
    return `${d.name}: 作業フローの磨き込み${steps ? `（${steps}）` : ""}`;
  }
  return "";
}

/** 月・水・金に置ける件数（9件の上限からじっくり枠の回数を引く） */
export function regularCap(s: Snapshot): number {
  return s.per_day * s.days.length - (s.deep_frame?.days.length || 0);
}

/** 9件の上限に数える件数（月水金に置いた件＋じっくり枠の回数） */
export function placedTotal(s: Snapshot, st: WeekState): number {
  const regular = Object.values(dayCounts(s, st)).reduce((a, b) => a + b, 0);
  return regular + (deepOf(s, st).kind !== "none" ? s.deep_frame?.days.length || 0 : 0);
}

export function dayCounts(s: Snapshot, st: WeekState): Record<string, number> {
  const out: Record<string, number> = Object.fromEntries(s.days.map((d) => [d, 0]));
  for (const d of Object.values(st.slots)) if (d && d in out) out[d] += 1;
  for (const v of Object.values(st.inlet)) if (v.action === "week" && v.day && v.day in out) out[v.day] += 1;
  return out;
}

export function weightOf(c: { weight?: Weight } | undefined): Weight {
  return c?.weight === "quick" || c?.weight === "deep" ? c.weight : "unknown";
}

export function weightLabel(s: Snapshot, w: Weight): string {
  return s.weight?.labels?.[w] || WEIGHT_LABEL[w];
}

/** いま置いている件（入口の今週やるも含む）の内訳。画面の「A n件／B n件」 */
export function placedWeights(s: Snapshot, st: WeekState): Record<Weight, number> {
  const out: Record<Weight, number> = { quick: 0, deep: 0, unknown: 0 };
  const byId = new Map(s.candidates.map((c) => [c.id, c]));
  for (const [id, d] of Object.entries(st.slots)) if (d) out[weightOf(byId.get(id))] += 1;
  for (const c of s.inlet) if (st.inlet[c.id]?.action === "week" && st.inlet[c.id]?.day) out[weightOf(c)] += 1;
  const d = deepOf(s, st);
  if (d.kind === "staff" || (d.kind === "task" && !st.slots[d.id])) out.deep += 1; // 枠の中身は「じっくり」1件
  return out;
}

/** じっくりが週の上限を超えて置かれているか（本人が足した時は止めずに知らせるだけ） */
export function deepOver(s: Snapshot, st: WeekState): number {
  const cap = s.weight?.deep_per_week;
  if (cap == null || !s.weight?.ok) return 0;
  return Math.max(0, placedWeights(s, st).deep - cap);
}

/** おすすめから翌週以降へ回したじっくりの理由 */
export function deferredReason(s: Snapshot, id: string): string | null {
  return s.weight?.deferred?.find((x) => x.id === id)?.reason || null;
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
  const deep = deepOf(s, st);
  const df = s.deep_frame;
  let deep_frame: Plan["deep_frame"] = null;
  const deepNotes: Plan["notes"] = [];
  if (df && deep.kind === "task" && !picked.has(deep.id)) {
    set_due.push({ id: deep.id, date: df.days[0] });
    picked.add(deep.id);
    const when = df.days.map((d, i) => `${i + 1}回目 ${dayLabel(d)}`).join("・");
    deepNotes.push({ id: deep.id, text: `週次：じっくり枠（週1件）。${when}` });
    deep_frame = { kind: "task", id: deep.id, days: df.days };
  } else if (df && deep.kind === "staff" && deep.name.trim()) {
    deep_frame = { kind: "staff", name: deep.name.trim(), days: df.days }; // Todoist には起票しない
  }
  const clear = new Set<string>();
  for (const x of s.dated_in_week) {
    if (!picked.has(x.id) && !x.hard && !st.keepDate[x.id]) clear.add(x.id);
  }
  const byId = new Map(s.candidates.map((c) => [c.id, c]));
  const notes: Plan["notes"] = [...deepNotes];
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
  return { set_due, clear_due: [...clear], notes, inlet, inlet_skip, deep_frame };
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
        weight: weightOf(c),
        weight_why: c.weight_why || null,
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

  if (s.deep_frame) {
    const d = deepOf(s, st);
    const init = initialDeep(s);
    const fromAi = JSON.stringify(d) === JSON.stringify(init);
    const common = { week: s.week, days: s.deep_frame.days, deep_frame: true, ai_choice: init, rule_version: s.rule_version };
    if (d.kind === "task") {
      const c = byId.get(d.id);
      out.push({
        ...base, action: "pick", targetType: "todoist_task", targetId: d.id, subject: c?.title || null,
        aiProposal: c?.weight_why || null, idemKey: key(`deep:${d.id}`),
        payload: { ...common, day: s.deep_frame.days[0], weight: weightOf(c), kept_ai: fromAi },
      });
    } else {
      out.push({
        ...base, action: d.kind === "staff" ? "pick" : "defer", targetType: "weekly_deep_frame", targetId: s.week,
        subject: d.kind === "staff" ? deepTitle(s, d) : null, idemKey: key("deep_frame"),
        payload: { ...common, staff: d.kind === "staff" ? d.name : null, decision_id: d.kind === "staff" ? d.decision_id || null : null, kept_ai: fromAi },
      });
    }
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
      weights: placedWeights(s, st),
      weight_basis: s.weight ? { ok: s.weight.ok, decision_id: s.weight.decision_id } : null,
      last: s.last,
      rule_version: s.rule_version,
      snapshot_at: s.generated_at,
    },
  });
  return out;
}
