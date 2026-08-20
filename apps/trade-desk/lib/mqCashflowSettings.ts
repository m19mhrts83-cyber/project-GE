/** 資金繰り起点設定 */

export type MqCashflowSettingsRow = {
  id?: string;
  business_line: string;
  entity: "personal" | "corporate";
  origin_month: string;
  initial_cash_man: number | string;
  tax_accrual_month?: string;
  note?: string | null;
};

export type MqCashflowSettings = {
  businessLine: string;
  entity: "personal" | "corporate";
  originMonth: string; // YYYY-MM
  initialCashMan: number;
  taxAccrualMonth: "december" | "payment";
  note: string | null;
};

export const DEFAULT_CORPORATE_CASHFLOW_SETTINGS: MqCashflowSettings = {
  businessLine: "realestate",
  entity: "corporate",
  originMonth: "2025-01",
  initialCashMan: 10,
  taxAccrualMonth: "december",
  note: "法人設立・資本金10万円（既定）",
};

function num(v: number | string | null | undefined): number {
  const x = Number(v);
  return Number.isFinite(x) ? x : 0;
}

export function normalizeCashflowSettings(
  raw: Partial<MqCashflowSettingsRow> | null | undefined
): MqCashflowSettings | null {
  if (!raw?.entity || !raw.origin_month) return null;
  return {
    businessLine: String(raw.business_line || "realestate"),
    entity: raw.entity as "personal" | "corporate",
    originMonth: String(raw.origin_month).slice(0, 7),
    initialCashMan: num(raw.initial_cash_man),
    taxAccrualMonth:
      raw.tax_accrual_month === "payment" ? "payment" : "december",
    note: raw.note ?? null,
  };
}

export function settingsForEntity(
  rows: MqCashflowSettingsRow[],
  businessLine: string,
  entity: "personal" | "corporate"
): MqCashflowSettings | null {
  const hit = rows.find(
    (r) => r.business_line === businessLine && r.entity === entity
  );
  return normalizeCashflowSettings(hit);
}

/** 当該年1月の期首現金（設定 or null） */
export function openingCashFromSettings(
  settings: MqCashflowSettings | null,
  year: number
): number | null {
  if (!settings) return null;
  const originYear = Number(settings.originMonth.slice(0, 4));
  if (year < originYear) return null;
  if (year === originYear) return settings.initialCashMan;
  return null; // 翌年以降は前年末繰越
}

export function originYearOf(settings: MqCashflowSettings | null): number | null {
  if (!settings) return null;
  return Number(settings.originMonth.slice(0, 4));
}
