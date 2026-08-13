/**
 * ③-A 簡易 DSCR（業界定番指標の取り入れ）
 * 厳密 NOI ではなく、レントロール月額 ÷ 月返済（簡易カバレッジ）。
 * 目安: 1.2 以上が融資・余裕の参考ライン。
 */

export function simpleDscr(
  rentMonth: number | null | undefined,
  payMonth: number | null | undefined
): number | null {
  if (rentMonth == null || payMonth == null) return null;
  if (!(payMonth > 0) || !(rentMonth >= 0)) return null;
  return Math.round((rentMonth / payMonth) * 100) / 100;
}

export function dscrLabel(d: number | null): string {
  if (d == null || !Number.isFinite(d)) return "—";
  if (d < 1) return "危険";
  if (d < 1.2) return "余裕薄";
  if (d < 1.5) return "標準";
  return "余裕";
}

export function fmtDscr(d: number | null): string {
  if (d == null || !Number.isFinite(d)) return "—";
  return `${d.toFixed(2)}×`;
}
