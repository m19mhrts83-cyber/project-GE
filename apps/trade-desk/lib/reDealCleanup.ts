/**
 * L-15: 候補一括整理の判定。
 * 対象は status=info のみ。問合せ進行・フォロー・Grok「聞く」は一覧に出さない。
 */
import { isExplicitFollowFlag, type PursueDealFields } from "./reDealPursue";
import { scoreBand } from "./reDealScoreUi";

export const CLEANUP_STALE_DAYS = 30;
export const CLEANUP_MAX_PER_BATCH = 20;
export const CLEANUP_UNDO_HOURS = 24;

export type CleanupReason = "low_score" | "out_of_area" | "stale_30d";

export type CleanupDealFields = PursueDealFields & {
  created_at?: string | null;
};

export type CleanupCandidate = {
  id: string;
  title: string;
  area: string | null;
  match_score: number | null;
  updated_at: string | null;
  age_days: number;
  reasons: CleanupReason[];
  default_checked: boolean;
};

const INQUIRY_ACTIVE = new Set([
  "sent",
  "sending",
  "awaiting_reply",
  "awaiting_grok",
  "has_reply",
]);

/** 東海コア＋周辺のヒット語（area/title に無ければエリア外） */
const CORE_AREA_RE =
  /愛知|岐阜|三重|大阪|名古屋|岡崎|碧南|知多|安城|豊田|瀬戸|春日井|犬山|一宮|各務原|大垣|桑名|四日市|津|鈴鹿|門真|豊明|刈谷|西尾|蒲郡|半田|東海市|常滑|みよし|日進|長久手/;

function sjOf(d: CleanupDealFields): Record<string, unknown> {
  const sj = d.summary_json;
  return sj && typeof sj === "object" ? sj : {};
}

function inquiryOf(d: CleanupDealFields): string {
  const sj = sjOf(d);
  return (
    d.inquiry_status ||
    (typeof sj.inquiry_status === "string" ? sj.inquiry_status : "none") ||
    "none"
  );
}

function listenValue(d: CleanupDealFields): string {
  const g = sjOf(d).grok;
  if (g && typeof g === "object") {
    const lv = (g as Record<string, unknown>).listen_value;
    return typeof lv === "string" ? lv : "";
  }
  return "";
}

function ageDays(updatedAt: string | null | undefined, nowMs: number): number {
  if (!updatedAt) return 999;
  const t = Date.parse(updatedAt);
  if (Number.isNaN(t)) return 999;
  return Math.floor((nowMs - t) / (24 * 60 * 60 * 1000));
}

export function isOutOfTargetArea(d: CleanupDealFields): boolean {
  const blob = `${d.area || ""} ${d.title || ""}`;
  if (!blob.trim()) return true;
  return !CORE_AREA_RE.test(blob);
}

export function isLowScore(d: CleanupDealFields): boolean {
  const band = scoreBand(d.match_score);
  return band === "low" || band === "none";
}

export function isStale(
  d: CleanupDealFields,
  nowMs = Date.now(),
  days = CLEANUP_STALE_DAYS
): boolean {
  return ageDays(d.updated_at, nowMs) >= days;
}

/** ハード除外: 一覧に出さない */
export function isCleanupHardExcluded(d: CleanupDealFields): boolean {
  const st = String(d.status || "");
  if (st !== "info") return true;
  if (INQUIRY_ACTIVE.has(inquiryOf(d))) return true;
  if (isExplicitFollowFlag(d)) return true;
  if (listenValue(d) === "聞く") return true;
  return false;
}

export function cleanupReasons(
  d: CleanupDealFields,
  nowMs = Date.now()
): CleanupReason[] {
  const reasons: CleanupReason[] = [];
  if (isLowScore(d)) reasons.push("low_score");
  if (isOutOfTargetArea(d)) reasons.push("out_of_area");
  if (isStale(d, nowMs)) reasons.push("stale_30d");
  return reasons;
}

export const CLEANUP_REASON_LABEL: Record<CleanupReason, string> = {
  low_score: "低スコア",
  out_of_area: "エリア外",
  stale_30d: `${CLEANUP_STALE_DAYS}日放置`,
};

/**
 * 整理候補を返す（理由が1つ以上あるものだけ）。上限で切る。
 */
export function buildCleanupCandidates(
  deals: CleanupDealFields[],
  opts?: { nowMs?: number; limit?: number }
): CleanupCandidate[] {
  const nowMs = opts?.nowMs ?? Date.now();
  const limit = opts?.limit ?? CLEANUP_MAX_PER_BATCH;
  const rows: CleanupCandidate[] = [];

  for (const d of deals) {
    if (!d.id) continue;
    if (isCleanupHardExcluded(d)) continue;
    const reasons = cleanupReasons(d, nowMs);
    if (reasons.length === 0) continue;
    rows.push({
      id: d.id,
      title: String(d.title || "").slice(0, 120) || d.id,
      area: d.area || null,
      match_score:
        typeof d.match_score === "number" && !Number.isNaN(d.match_score)
          ? d.match_score
          : null,
      updated_at: d.updated_at || null,
      age_days: ageDays(d.updated_at, nowMs),
      reasons,
      default_checked: true,
    });
  }

  rows.sort((a, b) => {
    const sa = a.match_score ?? -1;
    const sb = b.match_score ?? -1;
    if (sa !== sb) return sa - sb;
    return b.age_days - a.age_days;
  });

  return rows.slice(0, limit);
}

export function isUndoBatchFresh(
  bulkCleanupAt: string | null | undefined,
  nowMs = Date.now(),
  hours = CLEANUP_UNDO_HOURS
): boolean {
  if (!bulkCleanupAt) return false;
  const t = Date.parse(bulkCleanupAt);
  if (Number.isNaN(t)) return false;
  return nowMs - t <= hours * 60 * 60 * 1000;
}
