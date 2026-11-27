/**
 * 戦力の推移（/policy）。Mac の scripts/jarvis_force_monthly.py が Zaim CSV から集計して
 * sync_meta `force_monthly` に写した値を読む。金額はここ（公開リポ）に置かない。
 */
export type ForceService = { id: string; label: string; group: "ai" | "base" };

export type ForceMonthly = {
  generated_at: string;
  months: string[];
  services: ForceService[];
  amounts: Record<string, Record<string, number>>;
  /** ai-usage の月ごとの詰まり。記録が無ければ null */
  usage: Record<string, { blocked_days: number }> | null;
};

export function parseForceMonthly(raw: string | null | undefined): ForceMonthly | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as ForceMonthly;
    if (!v || !Array.isArray(v.months) || !Array.isArray(v.services) || typeof v.amounts !== "object") return null;
    return { ...v, usage: v.usage ?? null };
  } catch {
    return null;
  }
}

/**
 * AI 顧問料（sync_meta `advisory_fee`）。Zaim からは拾えないので別に持つ。
 * 固定分は fixed_from の月から、追加費用（改修対応など）は月ごとに手で入れる。
 */
export type AdvisoryFee = { fixed_yen: number; fixed_from: string | null; extras: Record<string, number> };

export function parseAdvisoryFee(raw: string | null | undefined): AdvisoryFee | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<AdvisoryFee>;
    if (!v || typeof v !== "object") return null;
    const extras: Record<string, number> = {};
    for (const [k, n] of Object.entries(v.extras || {})) {
      if (/^\d{4}-\d{2}$/.test(k) && Number.isFinite(Number(n)) && Number(n) >= 0) extras[k] = Math.round(Number(n));
    }
    return {
      fixed_yen: Number.isFinite(Number(v.fixed_yen)) ? Math.max(0, Math.round(Number(v.fixed_yen))) : 0,
      fixed_from: typeof v.fixed_from === "string" && /^\d{4}-\d{2}$/.test(v.fixed_from) ? v.fixed_from : null,
      extras,
    };
  } catch {
    return null;
  }
}

export type MonthRow = {
  ym: string;
  ai: number;
  base: number;
  total: number;
  fixed: number | null;
  extra: number | null;
  /** 固定＋追加（どちらも無い月は null） */
  income: number | null;
  /** 顧問料 − 支出（顧問料が無い月は null） */
  diff: number | null;
  /** 支出 ÷ 顧問料（％・顧問料が無い月は null） */
  ratioPct: number | null;
  blockedDays: number | null;
};

export function monthRows(p: ForceMonthly, fee: AdvisoryFee | null = null): MonthRow[] {
  const group = new Map(p.services.map((s) => [s.id, s.group]));
  return p.months.map((ym) => {
    let ai = 0;
    let base = 0;
    for (const [sid, yen] of Object.entries(p.amounts[ym] || {})) {
      if (group.get(sid) === "ai") ai += yen;
      else base += yen;
    }
    const total = ai + base;
    const fixed = fee && fee.fixed_yen > 0 && fee.fixed_from && ym >= fee.fixed_from ? fee.fixed_yen : null;
    const extra = fee && ym in fee.extras ? fee.extras[ym] : null;
    const inc = fixed == null && extra == null ? null : (fixed ?? 0) + (extra ?? 0);
    const hasInc = inc != null && inc > 0;
    return {
      ym,
      ai,
      base,
      total,
      fixed,
      extra,
      income: hasInc ? inc : null,
      diff: hasInc ? inc - total : null,
      ratioPct: hasInc ? (total / inc) * 100 : null,
      blockedDays: p.usage?.[ym]?.blocked_days ?? null,
    };
  });
}

export function monthLabel(ym: string): string {
  return `${Number(ym.slice(5, 7))}月`;
}
