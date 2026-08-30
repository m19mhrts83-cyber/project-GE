/** DB の timestamptz（UTC）を Asia/Tokyo の壁時計で表示。slice(0,16) は UTC のままなので使わない。 */
export function formatJstDateTime(
  iso: string | null | undefined,
  opts?: { seconds?: boolean }
): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16).replace("T", " ");
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: opts?.seconds ? "2-digit" : undefined,
    hour12: false,
  }).formatToParts(d);
  const g = (t: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === t)?.value || "";
  const base = `${g("year")}-${g("month")}-${g("day")} ${g("hour")}:${g("minute")}`;
  return opts?.seconds ? `${base}:${g("second")}` : base;
}

export function fmtYen(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `${Math.round(Number(n)).toLocaleString("ja-JP")}円`;
}

/** 差用。プラスは実績が多い（費用なら使いすぎ）。 */
export function fmtYenSigned(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Math.round(Number(n));
  const body = `${Math.abs(v).toLocaleString("ja-JP")}円`;
  if (v > 0) return `+${body}`;
  if (v < 0) return `−${body}`;
  return "±0円";
}

export function fmtMan(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n) / 10_000;
  const abs = Math.abs(v);
  const s = abs >= 100 ? v.toFixed(0) : v.toFixed(1);
  return `${s}万`;
}

/** 円 → 万円（四捨五入）。ざっくり把握用。 */
export function fmtManRounded(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "要確認";
  const man = Math.round(Number(n) / 10_000);
  return `${man.toLocaleString("ja-JP")}万`;
}

/** Numbers キャッシュフローのセル値（すでに万円）。 */
export function fmtManUnit(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  const abs = Math.abs(v);
  const s = abs >= 100 ? v.toFixed(0) : abs >= 10 ? v.toFixed(1) : v.toFixed(1);
  return `${s}万`;
}

export function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `${(Number(n) * 100).toFixed(digits)}%`;
}

/** 増減率。プラスに符号を付ける。 */
export function fmtPctSigned(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n) * 100;
  const body = `${Math.abs(v).toFixed(digits)}%`;
  if (v > 0) return `+${body}`;
  if (v < 0) return `−${body}`;
  return "±0%";
}

export function gainPct(
  value: number | null | undefined,
  cost: number | null | undefined
): number | null {
  const v = Number(value);
  const c = Number(cost);
  if (!Number.isFinite(v) || !Number.isFinite(c) || c === 0) return null;
  return (v - c) / c;
}

const DEFAULT_DASHBOARD_URL = "https://jarvis-dashboard-amber.vercel.app";

/** KURASHIFT 自身を指す誤設定だと /mail/* が 404 になるため弾く。 */
function resolveDashboardUrl(): string {
  const raw = (process.env.NEXT_PUBLIC_DASHBOARD_URL || "")
    .trim()
    .replace(/\/$/, "");
  if (!raw) return DEFAULT_DASHBOARD_URL;
  if (/jarvis-trade-desk|localhost:3003/i.test(raw)) return DEFAULT_DASHBOARD_URL;
  return raw;
}

export const DASHBOARD_URL = resolveDashboardUrl();

/** 借入残高トラッカー（ローン正本。Google: estate） */
export const LOAN_TRACKER_URL =
  process.env.NEXT_PUBLIC_LOAN_TRACKER_URL ||
  "https://loan-tracker-plum.vercel.app/";
