/**
 * AI社員・Grok Bot の週次稼働（/agent-team「週次稼働」タブ）。
 *
 * 数えるのは土曜 9:00 の scripts/jarvis_agent_weekly_activity.py（Mac・314 週次に相乗り）。
 * 最新の全体は sync_meta.agent_weekly_activity、週ごとの履歴は metrics(metric=agent_weekly_activity)。
 * 画面は読むだけ（数え方は config/agent_weekly_activity.yaml）。
 */
import { createServiceClient } from "@/lib/supabase/admin";

export type Signal = "🟢" | "🟡" | "🔴" | "⚪";

export type ActivityRow = {
  id: string;
  name: string;
  status: string;
  kind: "ai" | "grok";
  code?: string;
  expected: number | null;
  runs: number | null;
  worked: number | null;
  items: number | null;
  ok: number | null;
  ng: number | null;
  fail: number | null;
  retries?: number | null;
  pending: number | null;
  pending_samples?: string[];
  slack_posts: number;
  slack_signals: Partial<Record<Signal, number>>;
  last_at: string | null;
  sources: string[];
  notes: string[];
  signal: Signal;
  why: string;
  kinds?: Record<string, number>;
  kinds_expected?: Record<string, number>;
  outcomes?: Record<string, number>;
};

export type ActivityReport = {
  generated_at: string;
  since: string;
  until: string;
  summary: Record<Signal, number>;
  worked_agents: number;
  total_agents: number;
  agents: ActivityRow[];
  grok: ActivityRow[];
  attention: { id: string; name: string; signal: Signal; why: string }[];
  errors: string[];
};

export const SIGNAL_ORDER: Signal[] = ["🔴", "🟡", "🟢", "⚪"];

export const SIGNAL_LABEL: Record<Signal, string> = {
  "🟢": "回っている",
  "🟡": "遅れ・詰まり",
  "🔴": "止まっている",
  "⚪": "未計測・出番なし",
};

/** 先週の件数（metrics の1つ前の週）。id → 件数 */
export type PrevMap = Record<string, { items: number; runs: number | null; signal?: Signal }>;

export function parseReport(raw: unknown): ActivityReport | null {
  if (!raw) return null;
  try {
    const v = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!v || !Array.isArray(v.agents)) return null;
    return v as ActivityReport;
  } catch {
    return null;
  }
}

export function rowValue(r: Pick<ActivityRow, "items" | "worked" | "runs">): number {
  return r.items ?? r.worked ?? r.runs ?? 0;
}

/** 先週比（件数）。先週の記録がなければ null */
export function deltaOf(r: ActivityRow, prev: PrevMap): number | null {
  const p = prev[r.id];
  if (!p) return null;
  return rowValue(r) - p.items;
}

export function md(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(Date.parse(iso) + 9 * 3600_000);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}

export async function loadWeeklyActivity(): Promise<{ report: ActivityReport | null; prev: PrevMap; error?: string }> {
  const sb = createServiceClient();
  if (!sb) return { report: null, prev: {}, error: "Supabase 未設定" };
  const meta = await sb.from("sync_meta").select("value,updated_at").eq("key", "agent_weekly_activity").maybeSingle();
  if (meta.error) return { report: null, prev: {}, error: meta.error.message };
  const report = parseReport(meta.data?.value);
  if (!report) return { report: null, prev: {} };
  const day = report.until.slice(0, 10);
  const hist = await sb
    .from("metrics")
    .select("entity,value,recorded_at,payload")
    .eq("metric", "agent_weekly_activity")
    .lt("recorded_at", day)
    .order("recorded_at", { ascending: false })
    .limit(200);
  const prev: PrevMap = {};
  const rows = (hist.data || []) as { entity: string; value: number; recorded_at: string; payload: Record<string, unknown> }[];
  const lastDay = rows[0]?.recorded_at;
  for (const r of rows) {
    if (r.recorded_at !== lastDay) continue;
    const p = r.payload || {};
    prev[r.entity] = {
      items: Number(r.value) || 0,
      runs: typeof p.runs === "number" ? (p.runs as number) : null,
      signal: (p.signal as Signal) || undefined,
    };
  }
  return { report, prev };
}
