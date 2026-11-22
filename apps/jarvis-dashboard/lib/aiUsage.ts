/**
 * AI 使用量（/ai-usage）。Mac の scripts/jarvis_ai_usage_snapshot.py が sync_meta `ai_usage_now` に写した値を読む。
 * 値の古さと「回復時刻を過ぎたか」は、写した時ではなく画面を開いた時刻で判定し直す
 * （写してから時間がたった値を、新しい値のように見せないため）。
 */

export type AiUsageRow = {
  agent: string;
  agent_label: string;
  window: string;
  label: string;
  used_percent: number | null;
  resets_at: string | null;
  observed_at: string | null;
  note?: string | null;
};

export type AiUsageVerdict = {
  agent: string;
  level: "ok" | "keep" | "warn" | "unknown";
  title: string;
  detail: string;
  pace_percent?: number | null;
  pro_multiple?: number | null;
  streak_weeks?: number;
};

export type AiUsageHistoryEntry = { resets_at: string; peak: number; seen_at?: string | null };

export type AiUsagePayload = {
  generated_at: string;
  rows: AiUsageRow[];
  verdicts: AiUsageVerdict[];
  history: Record<string, AiUsageHistoryEntry[]>;
  assumptions?: {
    max_to_pro?: number;
    pro_ok_below?: number;
    weeks_needed?: number;
    stale_min?: number;
    status?: string;
  };
};

export type AiUsageRowView = AiUsageRow & {
  ageMin: number | null;
  /** 値が古い（判断に使えない） */
  stale: boolean;
  /** 回復時刻を過ぎた（この数字はもう前の枠のもの） */
  resetPassed: boolean;
};

const DEFAULT_STALE_MIN = 180;

export function parseAiUsage(raw: string | null | undefined): AiUsagePayload | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as AiUsagePayload;
    if (!v || typeof v !== "object" || !Array.isArray(v.rows)) return null;
    return { ...v, verdicts: Array.isArray(v.verdicts) ? v.verdicts : [], history: v.history || {} };
  } catch {
    return null;
  }
}

export function viewRows(p: AiUsagePayload, nowMs: number): AiUsageRowView[] {
  const staleMin = p.assumptions?.stale_min ?? DEFAULT_STALE_MIN;
  return p.rows.map((r) => {
    const seen = r.observed_at ? Date.parse(r.observed_at) : NaN;
    const ageMin = Number.isNaN(seen) ? null : Math.max(0, Math.round((nowMs - seen) / 60000));
    const reset = r.resets_at ? Date.parse(r.resets_at) : NaN;
    return {
      ...r,
      ageMin,
      stale: ageMin == null || ageMin > staleMin,
      resetPassed: !Number.isNaN(reset) && reset <= nowMs,
    };
  });
}

/** 判断の目安も、元の値が古くなっていたら「判断できない」に落とす。 */
export function viewVerdicts(p: AiUsagePayload, rows: AiUsageRowView[]): AiUsageVerdict[] {
  const main: Record<string, string> = { claude: "weekly", codex: "weekly", cursor: "monthly" };
  return p.verdicts.map((v) => {
    if (v.level === "unknown") return v;
    const r = rows.find((x) => x.agent === v.agent && x.window === main[v.agent]);
    if (r && (r.stale || r.resetPassed)) {
      return {
        ...v,
        level: "unknown",
        title: `${r.agent_label}：値が古く、判断できません`,
        detail: `最後の値は ${r.used_percent ?? "—"}%（${ageText(r.ageMin)}）。新しい値が入ると判断が戻ります。`,
      };
    }
    return v;
  });
}

export function ageText(ageMin: number | null): string {
  if (ageMin == null) return "時刻不明";
  if (ageMin < 120) return `${ageMin}分前`;
  if (ageMin < 48 * 60) return `${Math.floor(ageMin / 60)}時間前`;
  return `${Math.floor(ageMin / 1440)}日前`;
}

export function historyRows(p: AiUsagePayload, key: string, nowMs: number) {
  return (p.history[key] || [])
    .map((e) => ({ ...e, closed: Date.parse(e.resets_at) <= nowMs }))
    .sort((a, b) => Date.parse(b.resets_at) - Date.parse(a.resets_at));
}
