/**
 * Zaim の週次見直し（費目の学習が正しかったか）。純粋な計算だけ（テスト用に分けてある）。
 * 元データ: watch_status(id=zaim_quality).payload.recent_fixes（Mac の学習係が置く）
 */
export type ZaimFix = { id: string; proposal: string; shop: string; amount: number | null; status: string; at: string | null };

export function toFix(row: Record<string, unknown>): ZaimFix | null {
  const id = String(row.id || "").trim();
  if (!id) return null;
  const amt = Number(row.amount);
  return {
    id,
    proposal: String(row.proposal || "").slice(0, 200),
    shop: String(row.shop || "").slice(0, 60),
    amount: Number.isFinite(amt) ? amt : null,
    status: String(row.status || "pending_confirm"),
    at: row.at ? String(row.at) : row.created_at ? String(row.created_at) : null,
  };
}

/** 確認待ち（ダッシュボードで確認済みにした束は除く） */
export function pendingFixes(payload: Record<string, unknown>): ZaimFix[] {
  const ack = String(payload.dashboard_ack_batch_id || "");
  const batch = String(payload.review_batch_id || "");
  const rows = Array.isArray(payload.recent_fixes) ? (payload.recent_fixes as Record<string, unknown>[]) : [];
  const out: ZaimFix[] = [];
  for (const r of rows) {
    const st = String(r.status || "pending_confirm");
    if (st !== "pending_confirm") continue;
    const bid = String(r.batch_id || batch || "");
    if (ack && bid && ack === bid) continue;
    const f = toFix(r);
    if (f) out.push(f);
  }
  return out;
}

/** 正しい／違う を payload に反映（ダッシュボードの confirmZaimFix と同じ数え方） */
export function applyVerdict(payload: Record<string, unknown>, id: string, next: "confirmed" | "disputed", now: string): { payload: Record<string, unknown>; found: boolean } {
  const p = { ...payload };
  const batch = String(p.review_batch_id || "");
  let found = false;
  const fixes = (Array.isArray(p.recent_fixes) ? (p.recent_fixes as Record<string, unknown>[]) : []).map((f) => {
    if (String(f.id || "") !== id) return f;
    found = true;
    const row: Record<string, unknown> = { ...f, status: next, flagged_at: next === "disputed" ? now : null };
    if (next === "confirmed") row.confirmed_at = now;
    if (batch && !String(row.batch_id || "")) row.batch_id = batch;
    return row;
  });
  p.recent_fixes = fixes;
  const ack = String(p.dashboard_ack_batch_id || "");
  p.pending_confirm_count = fixes.filter((f) => {
    const st = String(f.status || "pending_confirm");
    const bid = String(f.batch_id || batch || "");
    if (ack && bid && ack === bid) return false;
    return st === "pending_confirm" || st === "disputed";
  }).length;
  return { payload: p, found };
}
