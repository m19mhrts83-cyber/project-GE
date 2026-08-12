/** 財務「直したよ」ピン — 確認するまでホームに残す */

export function zaimPendingConfirmCount(payload: Record<string, unknown>): number {
  const n = Number(payload.pending_confirm_count);
  if (Number.isFinite(n) && n > 0) return Math.floor(n);
  const fixes = Array.isArray(payload.recent_fixes)
    ? (payload.recent_fixes as Record<string, unknown>[])
    : [];
  return fixes.filter(
    (f) => !f.status || f.status === "pending_confirm",
  ).length;
}

/** ホーム最上段ピン／要フォローに出すか */
export function zaimWatchVisibleOnHome(payload: unknown): boolean {
  const pl =
    payload && typeof payload === "object"
      ? (payload as Record<string, unknown>)
      : {};
  if (pl.show_banner === true) return true;
  return zaimPendingConfirmCount(pl) > 0;
}
