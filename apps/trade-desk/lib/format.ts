export function fmtYen(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `${Math.round(Number(n)).toLocaleString("ja-JP")}円`;
}

export function fmtMan(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n) / 10_000;
  const abs = Math.abs(v);
  const s = abs >= 100 ? v.toFixed(0) : v.toFixed(1);
  return `${s}万`;
}

export function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `${(Number(n) * 100).toFixed(digits)}%`;
}

export const DASHBOARD_URL =
  process.env.NEXT_PUBLIC_DASHBOARD_URL ||
  "https://jarvis-dashboard-amber.vercel.app";
