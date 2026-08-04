/** Supabase timestamptz 等を Asia/Tokyo で表示 */

const JST = "Asia/Tokyo";

function fromParts(d: Date, withYear: boolean): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: JST,
    year: withYear ? "numeric" : undefined,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value || "";
  if (withYear) {
    return `${get("year")}/${get("month")}/${get("day")} ${get("hour")}:${get("minute")}`;
  }
  return `${get("month")}/${get("day")} ${get("hour")}:${get("minute")}`;
}

/** ISO っぽいがパース不能な文字列は UTC 想定で再解釈（直切り出しで JST ずれしない） */
function coerceDate(value: string): Date | null {
  const d = new Date(value);
  if (!Number.isNaN(d.getTime())) return d;
  const m = String(value).match(
    /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/,
  );
  if (!m) return null;
  const asUtc = new Date(
    `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6] || "00"}Z`,
  );
  return Number.isNaN(asUtc.getTime()) ? null : asUtc;
}

/**
 * コメント・同期時刻など: `MM/DD HH:mm`（JST）
 */
export function formatJstMmDdHm(
  value: string | null | undefined,
  fallback = "—",
): string {
  if (!value) return fallback;
  const d = coerceDate(String(value));
  if (!d) return fallback;
  return fromParts(d, false);
}

/**
 * アーカイブ等: `YYYY/MM/DD HH:mm`（JST）
 */
export function formatJstYmdHm(
  value: string | null | undefined,
  fallback = "",
): string {
  if (!value) return fallback;
  const d = coerceDate(String(value));
  if (!d) return fallback;
  return fromParts(d, true);
}
