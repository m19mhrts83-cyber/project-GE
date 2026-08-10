/** 状況ウォッチ／オプチャ健全性の汎用「確認した」→ バッジ抑制と再表示 */

export const WATCH_ACK_QUIET_DAYS_DEFAULT = 7;

/** 専用「確認しました」がある ID（汎用ボタンは出さない） */
export const SPECIALIZED_ACK_WATCH_IDS = new Set([
  "etc_mileage",
  "vpoint",
  "rent_step",
  "zaim_quality",
  "ops_fix_notice",
]);

export type UserAck = {
  fingerprint?: string;
  acked_at?: string;
  quiet_until?: string;
  acked_level?: string;
};

export type WatchAckRow = {
  id?: string;
  level?: string | null;
  summary?: string | null;
  status?: string | null;
  payload?: Record<string, unknown> | null;
};

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

export function readUserAck(payload: unknown): UserAck | null {
  const pl = asRecord(payload);
  const ua = pl.user_ack;
  if (!ua || typeof ua !== "object") return null;
  return ua as UserAck;
}

/** openchat_threads 用指紋（TS ↔ Python で揃える） */
export function buildOpenchatAckFingerprint(payload: unknown, level?: string | null): string {
  const pl = asRecord(payload);
  const rem = asRecord(pl.remediation);
  const mf = asRecord(pl.main_freshness);
  const worst = String(pl.worst_level || level || "").trim();
  const symptom = String(rem.symptom || "").trim();
  const mainStale = Boolean(mf.stale || rem.main_stale || pl.main_stale);
  const writeErr = Boolean(
    pl.last_write_error || asRecord(pl.watch).last_write_error,
  );
  const routes = Array.isArray(pl.routes) ? pl.routes : [];
  const attentionIds = routes
    .filter((r) => r && typeof r === "object" && (r as { level?: string }).level === "attention")
    .map((r) => String((r as { route_id?: string }).route_id || "").trim())
    .filter(Boolean)
    .sort();
  return [
    "openchat",
    worst,
    symptom,
    mainStale ? "main1" : "main0",
    writeErr ? "err1" : "err0",
    attentionIds.join(","),
  ].join("|");
}

/** 一般 watch 用指紋（相対時間などを落として push ごとの揺れを防ぐ） */
export function normalizeSummaryForAck(summary: string | null | undefined): string {
  let s = String(summary || "").trim();
  // 「約 50 時間前」「3日前」「あと14日」など相対表現を正規化
  s = s.replace(/約\s*\d+\s*時間前/g, "時間前");
  s = s.replace(/\d+\s*時間前/g, "時間前");
  s = s.replace(/約\s*\d+\s*日前/g, "日前");
  s = s.replace(/\d+\s*日前/g, "日前");
  s = s.replace(/あと\s*\d+\s*日/g, "あとN日");
  s = s.replace(/残り\s*\d+\s*日/g, "残りN日");
  s = s.replace(/\d{4}-\d{2}-\d{2}T[\d:+.-]+/g, "TS");
  s = s.replace(/\d{4}\/\d{2}\/\d{2}\s+\d{2}:\d{2}/g, "DT");
  s = s.replace(/\s+/g, " ").trim();
  return s.slice(0, 120);
}

/** 一般 watch 用指紋 */
export function buildGenericAckFingerprint(
  id: string,
  level: string | null | undefined,
  summary: string | null | undefined,
): string {
  const sum120 = normalizeSummaryForAck(summary);
  return ["watch", id, String(level || "").trim(), sum120].join("|");
}

export function buildWatchAckFingerprint(row: WatchAckRow): string {
  const id = String(row.id || "").trim();
  if (id === "openchat_threads") {
    return buildOpenchatAckFingerprint(row.payload, row.level);
  }
  return buildGenericAckFingerprint(id, row.level, row.summary);
}

export function quietUntilIso(days = WATCH_ACK_QUIET_DAYS_DEFAULT, from = new Date()): string {
  const d = new Date(from.getTime());
  d.setUTCDate(d.getUTCDate() + Math.max(1, days));
  return d.toISOString();
}

export function isWatchAckActive(
  payload: unknown,
  currentFingerprint: string,
  now = new Date(),
): boolean {
  const ua = readUserAck(payload);
  if (!ua?.fingerprint || !ua.quiet_until) return false;
  if (String(ua.fingerprint) !== String(currentFingerprint)) return false;
  const until = Date.parse(String(ua.quiet_until));
  if (Number.isNaN(until)) return false;
  return now.getTime() < until;
}

export function formatQuietUntilLabel(quietUntil: string | undefined): string {
  if (!quietUntil) return "";
  const d = new Date(quietUntil);
  if (Number.isNaN(d.getTime())) return "";
  const y = d.getFullYear();
  const m = d.getMonth() + 1;
  const day = d.getDate();
  return `${y}-${String(m).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** ナビ／ホーム要フォローに出すか */
export function shouldShowWatchBadge(row: WatchAckRow, now = new Date()): boolean {
  if (row.status && row.status !== "active") return false;
  const level = String(row.level || "");
  if (level !== "attention" && level !== "warn") return false;
  const fp = buildWatchAckFingerprint(row);
  if (isWatchAckActive(row.payload, fp, now)) return false;
  return true;
}

export function usesSpecializedAck(watchId: string): boolean {
  return SPECIALIZED_ACK_WATCH_IDS.has(watchId);
}

/** 汎用「確認した」ボタンを出すか（専用ページ確認がある項目も状況ウォッチから消せる） */
export function canShowGenericAckButton(row: WatchAckRow, now = new Date()): boolean {
  const id = String(row.id || "");
  if (!id) return false;
  // ops お知らせは専用ボタンのみ（ephemeral）
  if (id === "ops_fix_notice") return false;
  const level = String(row.level || "");
  if (level !== "attention" && level !== "warn") return false;
  const fp = buildWatchAckFingerprint(row);
  return !isWatchAckActive(row.payload, fp, now);
}
