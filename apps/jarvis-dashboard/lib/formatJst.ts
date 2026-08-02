/** Supabase timestamptz 等を Asia/Tokyo で表示 */

const JST = "Asia/Tokyo";

/**
 * コメント・同期時刻など: `MM/DD HH:mm`（JST）
 */
export function formatJstMmDdHm(
  value: string | null | undefined,
  fallback = "—",
): string {
  if (!value) return fallback;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    const m = String(value).match(
      /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/,
    );
    if (m) return `${m[2]}/${m[3]} ${m[4]}:${m[5]}`;
    return String(value).slice(0, 16) || fallback;
  }
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: JST,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value || "";
  return `${get("month")}/${get("day")} ${get("hour")}:${get("minute")}`;
}

/**
 * アーカイブ等: `YYYY/MM/DD HH:mm`（JST）
 */
export function formatJstYmdHm(
  value: string | null | undefined,
  fallback = "",
): string {
  if (!value) return fallback;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    const m = String(value).match(
      /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/,
    );
    if (m) return `${m[1]}/${m[2]}/${m[3]} ${m[4]}:${m[5]}`;
    return String(value).slice(0, 16) || fallback;
  }
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: JST,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value || "";
  return `${get("year")}/${get("month")}/${get("day")} ${get("hour")}:${get("minute")}`;
}
