/** Lifeplan UI triggers (not the daily HQ focus). */

export type LifeplanMode = "annual" | "re_purchase" | "default";

/** After Dec closes: Jan–Feb window to run annual actuals → budget → LP update. */
export function isAnnualLifeplanWindow(now = new Date()): boolean {
  const m = now.getMonth() + 1;
  return m === 1 || m === 2;
}

/** Fiscal year whose actuals just closed (for Jan 2026 → 2025). */
export function closedActualsFiscalYear(now = new Date()): number {
  return now.getFullYear() - 1;
}

/** Budget / forward plan year to update (for Jan 2026 → 2026). */
export function forwardPlanYear(now = new Date()): number {
  return now.getFullYear();
}

export function annualNoticeCopy(now = new Date()): {
  title: string;
  body: string;
  actualsYear: number;
  planYear: number;
} {
  const actualsYear = closedActualsFiscalYear(now);
  const planYear = forwardPlanYear(now);
  return {
    title: "年間実績が確定しました",
    body: `${actualsYear}年の実績が確定したので、${planYear}年以降のライフプランと予算を更新しましょう。`,
    actualsYear,
    planYear,
  };
}

export function parseLifeplanMode(
  raw: string | string[] | undefined
): LifeplanMode {
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (v === "annual" || v === "re_purchase") return v;
  return "default";
}
