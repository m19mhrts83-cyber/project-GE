export type WorkEvent = {
  id: string;
  at: string;
  item_id: string;
  kind: string;
  actor: string;
  summary: string;
  minutes: number | null;
  time_kind: "unrecorded" | "owner_confirmed" | "estimated" | "agent_elapsed";
  evidence: string[];
  question_id?: string;
  supersedes?: string;
};

export type WorkProject = {
  id: string;
  title: string;
  estimate_minutes: number | null;
  items: { id: string; title: string; status: string }[];
  events: WorkEvent[];
};

export type WorkHistory = { version: number; updated_at: string | null; projects: WorkProject[] };

export function parseWorkHistory(raw: unknown): WorkHistory | null {
  if (raw == null) return null;
  const value = typeof raw === "string" ? JSON.parse(raw) : raw;
  if (value?.version !== 1 || !Array.isArray(value.projects)) throw new Error("履歴の形式を確認してください");
  for (const p of value.projects) {
    if (typeof p.id !== "string" || typeof p.title !== "string" || !Array.isArray(p.items) || !Array.isArray(p.events)) throw new Error("案件の形式を確認してください");
    for (const i of p.items) {
      if (typeof i.id !== "string" || typeof i.title !== "string" || typeof i.status !== "string") throw new Error("項目の形式を確認してください");
    }
    for (const e of p.events) {
      if (typeof e.id !== "string" || typeof e.item_id !== "string" || typeof e.summary !== "string" || typeof e.at !== "string" || !Array.isArray(e.evidence)) throw new Error("実行履歴の形式を確認してください");
      if (e.minutes != null && (typeof e.minutes !== "number" || !Number.isFinite(e.minutes) || e.minutes < 0)) throw new Error("作業時間の形式を確認してください");
    }
  }
  return value as WorkHistory;
}

export function workTotals(events: WorkEvent[]) {
  const superseded = new Set(events.map(e => e.supersedes).filter(Boolean));
  const active = events.filter(e => !superseded.has(e.id));
  const total = (kind: WorkEvent["time_kind"]) => active.reduce((n, e) => n + (e.time_kind === kind ? e.minutes ?? 0 : 0), 0);
  return {
    confirmed: total("owner_confirmed"),
    estimated: total("estimated"),
    agent: total("agent_elapsed"),
    unrecorded: active.filter(e => e.minutes == null && e.kind === "log").length,
  };
}
