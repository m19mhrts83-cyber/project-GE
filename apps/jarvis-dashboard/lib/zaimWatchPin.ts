/** 財務「直したよ」ピン — 確認するまでホームに残す */

function isUnackedLearnFix(
  f: Record<string, unknown>,
  ack: string,
  reviewBatch: string,
): boolean {
  const st = String(f.status || "pending_confirm");
  if (st === "confirmed" || st === "failed") return false;
  if (st !== "pending_confirm" && st !== "disputed") return false;
  const bid = String(f.batch_id || reviewBatch || "");
  if (ack && bid && ack === bid) return false;
  return true;
}

export function zaimPendingConfirmCount(payload: Record<string, unknown>): number {
  const n = Number(payload.pending_confirm_count);
  if (Number.isFinite(n) && n > 0) return Math.floor(n);
  const ack = String(payload.dashboard_ack_batch_id || "");
  const reviewBatch = String(payload.review_batch_id || "");
  const fixes = Array.isArray(payload.recent_fixes)
    ? (payload.recent_fixes as Record<string, unknown>[])
    : [];
  return fixes.filter((f) => isUnackedLearnFix(f, ack, reviewBatch)).length;
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
