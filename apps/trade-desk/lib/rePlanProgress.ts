/**
 * ③-A 年計画 vs YTD（RE-1b）
 * 計画月次の正: CF 目標 50万（合算）。個人／法人は満室想定 CF を按分せず、
 * スコープ別は「想定CF（満室）×経過月」と「目標×経過月（合算のみ）」を併記。
 */

export type PlanProgress = {
  planMonthYen: number;
  planYtdYen: number;
  actualYtdYen: number;
  months: number;
  /** 0〜100+（超過可） */
  pct: number | null;
  deltaYen: number;
};

export function buildPlanProgress(opts: {
  planMonthYen: number;
  actualYtdYen: number;
  months: number;
}): PlanProgress {
  const months = Math.max(1, opts.months);
  const planYtdYen = Math.round(opts.planMonthYen * months);
  const actualYtdYen = Math.round(opts.actualYtdYen);
  const pct =
    planYtdYen > 0
      ? Math.round((actualYtdYen / planYtdYen) * 1000) / 10
      : null;
  return {
    planMonthYen: Math.round(opts.planMonthYen),
    planYtdYen,
    actualYtdYen,
    months,
    pct,
    deltaYen: actualYtdYen - planYtdYen,
  };
}
