export function fmtYen(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `${Math.round(Number(n)).toLocaleString("ja-JP")}円`;
}

export function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `${(Number(n) * 100).toFixed(1)}%`;
}

export const DASHBOARD_URL =
  process.env.NEXT_PUBLIC_DASHBOARD_URL ||
  "https://jarvis-dashboard-amber.vercel.app";
