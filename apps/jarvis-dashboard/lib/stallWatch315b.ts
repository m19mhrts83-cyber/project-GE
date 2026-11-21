/**
 * 315-B 300番台 停止・空回り監視（日次）の表示用データ。
 *
 * 書くのは Mac の scripts/jarvis_stall_watch_315b.py（毎日 08:20・18:20、既存の鮮度監視に相乗り）→ sync_meta.stall_watch_315b。
 * 画面（/agent-team「週次稼働」タブの先頭）は読むだけ。判定・通知は Mac 側で済んでいる。
 * 結果の保存（save）と画面反映は別々に成否を持つ。ここに来ている＝画面反映は成功した回。
 */

export type StallStatus = "ok" | "stale" | "idle" | "unknown";

export type StallRow = {
  id: string;
  label: string;
  owner?: string;
  status: StallStatus;
  why: string;
  last: string | null;
  age_h: number | null;
  max_age_h: number | null;
  stop_status?: string;
  idle_status?: string;
  idle_why?: string | null;
  missing?: string[];
};

export type StallReport = {
  run_id: string;
  checked_at: string;
  result: "success" | "partial" | "failure";
  result_why: string[];
  save: { ok: boolean; why?: string } | null;
  rows: StallRow[];
  pending: { id: string; kind: string; to: string }[];
};

export const STALL_LABEL: Record<StallStatus, string> = {
  ok: "正常",
  stale: "遅れ",
  idle: "空回り",
  unknown: "読取不可",
};

export const STALL_SIGNAL: Record<StallStatus, "🟢" | "🟡" | "🔴"> = {
  ok: "🟢",
  stale: "🔴",
  idle: "🔴",
  unknown: "🟡",
};

export const RESULT_LABEL: Record<StallReport["result"], string> = {
  success: "成功",
  partial: "部分成功",
  failure: "失敗",
};

const RANK: Record<StallStatus, number> = { unknown: 1, stale: 0, idle: 2, ok: 3 };
const STATUSES = new Set<StallStatus>(["ok", "stale", "idle", "unknown"]);

export function parseStallReport(raw: unknown): StallReport | null {
  if (!raw) return null;
  try {
    const v = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!v || typeof v !== "object" || !Array.isArray(v.rows) || typeof v.checked_at !== "string") return null;
    const rows = (v.rows as StallRow[]).filter((r) => r && typeof r.id === "string" && STATUSES.has(r.status));
    return {
      run_id: String(v.run_id || ""),
      checked_at: v.checked_at,
      result: v.result === "success" || v.result === "partial" || v.result === "failure" ? v.result : "partial",
      result_why: Array.isArray(v.result_why) ? v.result_why.map(String) : [],
      save: v.save && typeof v.save === "object" ? v.save : null,
      rows,
      pending: Array.isArray(v.pending) ? v.pending : [],
    };
  } catch {
    return null;
  }
}

/** 異常（遅れ→読取不可→空回り）を先に、同じなら社員番号順。 */
export function sortStallRows(rows: StallRow[]): StallRow[] {
  return [...rows].sort((a, b) => RANK[a.status] - RANK[b.status] || a.id.localeCompare(b.id));
}

/** 監視が古い（2 回分＝おおむね 14h を超えて更新がない）なら、画面の判定は当てにしない。 */
export function isStallReportOld(r: Pick<StallReport, "checked_at">, now = Date.now(), maxH = 15): boolean {
  const t = Date.parse(r.checked_at);
  return Number.isNaN(t) || now - t > maxH * 3600_000;
}

export function ageText(h: number | null | undefined): string {
  if (h == null) return "—";
  if (h >= 48) return `${(h / 24).toFixed(1)}日前`;
  if (h >= 1) return `${Math.round(h)}時間前`;
  return `${Math.round(h * 60)}分前`;
}
