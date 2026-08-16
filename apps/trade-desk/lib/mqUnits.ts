/**
 * MQ会計の金額単位: 万円。円→万は四捨五入。
 * DB・手入力・表示はいずれも万円を正とする。
 */

export const MQ_YEN_PER_MAN = 10_000;

/** 円 → 万円（四捨五入） */
export function yenToMan(yen: number | null | undefined): number {
  if (yen == null || yen === ("" as unknown)) return 0;
  const n = Number(yen);
  if (!Number.isFinite(n)) return 0;
  return Math.round(n / MQ_YEN_PER_MAN);
}

/** 既に万円の値を整数へ四捨五入 */
export function roundMan(man: number | null | undefined): number {
  if (man == null || man === ("" as unknown)) return 0;
  const n = Number(man);
  if (!Number.isFinite(n)) return 0;
  return Math.round(n);
}

export function yenToManOrNull(
  yen: number | null | undefined
): number | null {
  if (yen == null || yen === ("" as unknown)) return null;
  const n = Number(yen);
  if (!Number.isFinite(n)) return null;
  return Math.round(n / MQ_YEN_PER_MAN);
}

export function roundManOrNull(
  man: number | null | undefined
): number | null {
  if (man == null || man === ("" as unknown)) return null;
  const n = Number(man);
  if (!Number.isFinite(n)) return null;
  return Math.round(n);
}

/** 表示: 825万 / — */
export function fmtMqMan(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(Number(n))) return "—";
  return `${roundMan(n).toLocaleString("ja-JP")}万`;
}

export function fmtMqManSigned(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(Number(n))) return "—";
  const v = roundMan(n);
  const body = `${Math.abs(v).toLocaleString("ja-JP")}万`;
  if (v > 0) return `+${body}`;
  if (v < 0) return `−${body}`;
  return "±0万";
}
